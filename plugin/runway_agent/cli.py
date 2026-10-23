"""runway-agent: the controller's CLI, plus the two worker-side commands (claim-check, receipt).

Controller commands read and write ~/.runway-agent/runway.db (RUNWAY_AGENT_HOME overrides).
Worker commands never open the database; they read the dispatch packet and write the outbox.
"""

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone

from . import gate, receipts, review, store, transport


def _out(data, as_json):
    if as_json:
        print(json.dumps(data, indent=2, default=str))
        return True
    return False


def _text(args, name):
    """--body or --body-file, and the same for acceptance."""
    value = getattr(args, name)
    path = getattr(args, f"{name}_file", None)
    if path:
        value = sys.stdin.read() if path == "-" else open(path).read()
    return value or ""


def cmd_init(args, conn):
    print(f"store ready at {store.home() / 'runway.db'}")


def cmd_project_add(args, conn):
    store.add_project(conn, args.key, args.name or args.key, args.repo, args.path, args.default_branch)
    print(f"project {args.key} -> {args.repo}")


def cmd_machine_add(args, conn):
    store.add_machine(conn, args.label, args.kind, args.ssh_host, args.herdr_label)
    print(f"machine {args.label} ({args.kind})")


def cmd_ticket_add(args, conn):
    ticket_ref = store.add_ticket(
        conn, args.project, args.title, _text(args, "body"), args.risk, args.risk_reason, args.strategy,
        args.spec, args.plan, _text(args, "acceptance"), "\n".join(args.touches or []), args.model,
        args.blocked_by or [])
    print(ticket_ref)


def cmd_ticket_list(args, conn):
    rows = store.list_tickets(conn, args.project, args.status)
    if _out([dict(r) for r in rows], args.json):
        return
    for r in rows:
        print(f"{r['key']}-{r['number']:<5} {r['status']:<10} {r['risk']:<8} {r['title']}")


def cmd_ticket_show(args, conn):
    t = store.ticket_by_ref(conn, args.ref)
    events = [dict(e, payload=json.loads(e["payload"])) for e in store.events_for(conn, t["id"])]
    comments = [dict(c) for c in conn.execute("select * from comments where ticket_id = ? order by id", (t["id"],))]
    data = {**dict(t), "ref": args.ref, "blocked_by_open": store.blockers_open(conn, t["id"]),
            "comments": comments, "events": events}
    if _out(data, args.json):
        return
    print(f"{args.ref}  {t['title']}\nstatus {t['status']}, risk {t['risk']}"
          + (f" ({t['risk_reason']})" if t["risk_reason"] else ""))
    for label, key in (("spec", "spec_path"), ("plan", "plan_path")):
        if t[key]:
            print(f"{label}: {t[key]}")
    if data["blocked_by_open"]:
        print("blocked by: " + ", ".join(data["blocked_by_open"]))
    for e in events:
        print(f"  {e['at']}  {e['kind']}")


def cmd_ticket_comment(args, conn):
    store.add_comment(conn, store.ticket_by_ref(conn, args.ref)["id"], args.author, args.body)


def cmd_ticket_drop(args, conn):
    t = store.ticket_by_ref(conn, args.ref)
    with store.tx(conn):
        store.append_event(conn, "dropped", t["id"], payload={"by": args.by, "reason": args.reason})


def cmd_dispatch(args, conn):
    packet = store.dispatch(conn, args.ref, args.machine)
    if args.launch:
        machine = store.machine_by_label(conn, args.machine)
        packet["herdr_session"] = transport.launch(conn, machine, packet)
    print(json.dumps(packet, indent=2))


def cmd_pull(args, conn):
    labels = [args.machine] if args.machine else [
        m["label"] for m in conn.execute("select label from machines where enabled = 1 and kind != 'cloud'")]
    for label in labels:
        machine = store.machine_by_label(conn, label)
        try:
            lines = transport.read_outbox(machine)
        except transport.TransportError as e:
            print(f"{label}: unreachable ({e})", file=sys.stderr)
            continue
        added, dup, rejected = receipts.apply(conn, lines, label)
        print(f"{label}: {added} new, {dup} already had, {rejected} rejected")


def cmd_reap(args, conn):
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=args.grace_minutes)
    for attempt in store.live_attempts(conn):
        machine = conn.execute("select * from machines where id = ?", (attempt["machine_id"],)).fetchone()
        state = args.state or transport.herdr_states(machine).get(str(attempt["herdr_session"]), "gone")
        last = conn.execute("select max(at) from events where attempt_id = ?", (attempt["id"],)).fetchone()[0]
        quiet = datetime.strptime(last, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) < cutoff
        if receipts.reap(conn, attempt, state, quiet):
            print(f"{attempt['dispatch_id']}: failed (Herdr says {state}, no closing receipt)")


def cmd_review_run(args, conn):
    available = transport.config().get("models", ["claude", "codex"])
    print(review.run(conn, args.ref, available))


def cmd_review_record(args, conn):
    print(review.record(conn, args.ref, args.verdict, args.commit, args.model, args.finding or [],
                        args.raise_risk, args.same_model))


def cmd_gate(args, conn):
    result = gate.run(conn, args.ref, dry_run=args.dry_run)
    if _out(result, args.json):
        return
    print(f"{args.ref}: {result['verdict']}" + ("".join(f"\n  - {r}" for r in result["reasons"])))


def cmd_decisions(args, conn):
    rows = store.open_decisions(conn)
    if _out([dict(r) for r in rows], args.json):
        return
    for d in rows:
        t = conn.execute("select * from tickets where id = ?", (d["ticket_id"],)).fetchone()
        print(f"#{d['id']} {store.ref(conn, t)} [{d['kind']}] {d['question']}"
              + (f" (recommended: {d['recommended']})" if d["recommended"] else ""))


def cmd_answer(args, conn):
    row = store.answer_decision(conn, args.id, args.answer, args.by)
    t = conn.execute("select * from tickets where id = ?", (row["ticket_id"],)).fetchone()
    ticket_ref = store.ref(conn, t)
    if row["kind"] == "gate":
        if args.answer == "merge":
            gate.approve(conn, ticket_ref, by=args.by)
        else:
            with store.tx(conn):
                store.append_event(conn, "dropped" if args.answer == "drop" else "reopened", t["id"],
                                   payload={"after_decision": row["id"]})
    print(f"{ticket_ref}: {store.ticket_by_ref(conn, ticket_ref)['status']}")


# --- worker side: never opens the database ---------------------------------------

def cmd_claim_check(args, conn):
    packet = receipts.load_packet(args.packet)
    receipts.claim_check(packet)
    print(f"claim ok: {packet['ticket']} on {packet['machine']} as {packet['dispatch_id']}")


def cmd_receipt(args, conn):
    packet = receipts.load_packet(args.packet)
    receipts.claim_check(packet)
    fields = dict(kv.split("=", 1) for kv in args.field or [])
    for name in ("worktree", "note", "head", "pr", "reason", "question", "recommended", "output", "model"):
        if getattr(args, name) is not None:
            fields[name] = getattr(args, name)
    if args.option:
        fields["options"] = args.option
    if "pr" in fields:
        fields["pr"] = int(str(fields["pr"]).lstrip("#"))
    r = receipts.write(packet, args.kind, **fields)
    print(f"{r['kind']} receipt {r['id']} written")


WORKER_COMMANDS = {"claim-check", "receipt"}


def parser():
    p = argparse.ArgumentParser(prog="runway-agent", description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="create the store").set_defaults(fn=cmd_init)

    proj = sub.add_parser("project").add_subparsers(dest="sub", required=True)
    a = proj.add_parser("add")
    a.add_argument("key"); a.add_argument("--name"); a.add_argument("--repo", required=True)
    a.add_argument("--path", help="the controller's clone"); a.add_argument("--default-branch", default="main")
    a.set_defaults(fn=cmd_project_add)

    mach = sub.add_parser("machine").add_subparsers(dest="sub", required=True)
    a = mach.add_parser("add")
    a.add_argument("label"); a.add_argument("--kind", choices=("local", "ssh", "cloud"), default="ssh")
    a.add_argument("--ssh-host"); a.add_argument("--herdr-label")
    a.set_defaults(fn=cmd_machine_add)

    tick = sub.add_parser("ticket").add_subparsers(dest="sub", required=True)
    a = tick.add_parser("add")
    a.add_argument("project"); a.add_argument("--title", required=True)
    a.add_argument("--body"); a.add_argument("--body-file")
    a.add_argument("--acceptance"); a.add_argument("--acceptance-file")
    a.add_argument("--risk", choices=store.RISKS, default="not-low"); a.add_argument("--risk-reason")
    a.add_argument("--strategy", choices=("single", "swarm"), default="single")
    a.add_argument("--spec"); a.add_argument("--plan"); a.add_argument("--model", choices=("claude", "codex"))
    a.add_argument("--touches", action="append"); a.add_argument("--blocked-by", action="append")
    a.set_defaults(fn=cmd_ticket_add)
    a = tick.add_parser("list")
    a.add_argument("--project"); a.add_argument("--status"); a.add_argument("--json", action="store_true")
    a.set_defaults(fn=cmd_ticket_list)
    a = tick.add_parser("show"); a.add_argument("ref"); a.add_argument("--json", action="store_true")
    a.set_defaults(fn=cmd_ticket_show)
    a = tick.add_parser("comment"); a.add_argument("ref"); a.add_argument("--author", required=True)
    a.add_argument("--body", required=True); a.set_defaults(fn=cmd_ticket_comment)
    a = tick.add_parser("drop"); a.add_argument("ref"); a.add_argument("--by", required=True)
    a.add_argument("--reason", default=""); a.set_defaults(fn=cmd_ticket_drop)

    a = sub.add_parser("dispatch", help="claim a ticket for a machine and print its packet")
    a.add_argument("ref"); a.add_argument("--machine", required=True)
    a.add_argument("--launch", action="store_true", help="also send the packet and start it through Herdr")
    a.set_defaults(fn=cmd_dispatch)

    a = sub.add_parser("pull", help="pull worker outboxes into the store")
    a.add_argument("--machine"); a.set_defaults(fn=cmd_pull)

    a = sub.add_parser("reap", help="fail live attempts whose session ended without a closing receipt")
    a.add_argument("--grace-minutes", type=int, default=10)
    a.add_argument("--state", help="use this Herdr state instead of asking Herdr")
    a.set_defaults(fn=cmd_reap)

    rev = sub.add_parser("review").add_subparsers(dest="sub", required=True)
    a = rev.add_parser("run"); a.add_argument("ref"); a.set_defaults(fn=cmd_review_run)
    a = rev.add_parser("record"); a.add_argument("ref")
    a.add_argument("--verdict", choices=review.VERDICTS, required=True)
    a.add_argument("--commit", required=True); a.add_argument("--model", required=True)
    a.add_argument("--finding", action="append"); a.add_argument("--raise-risk", action="store_true")
    a.add_argument("--same-model", action="store_true")
    a.set_defaults(fn=cmd_review_record)

    a = sub.add_parser("gate", help="merge a reviewed low-risk ticket, or stop it as needs-you")
    a.add_argument("ref"); a.add_argument("--dry-run", action="store_true"); a.add_argument("--json", action="store_true")
    a.set_defaults(fn=cmd_gate)

    a = sub.add_parser("decisions", help="open needs-you questions"); a.add_argument("--json", action="store_true")
    a.set_defaults(fn=cmd_decisions)
    a = sub.add_parser("answer"); a.add_argument("id", type=int); a.add_argument("answer")
    a.add_argument("--by", required=True); a.set_defaults(fn=cmd_answer)

    a = sub.add_parser("claim-check", help="worker: confirm this session holds the claim")
    a.add_argument("--packet", required=True); a.set_defaults(fn=cmd_claim_check)
    a = sub.add_parser("receipt", help="worker: append a typed receipt to the local outbox")
    a.add_argument("kind", choices=tuple(receipts.SCHEMAS)); a.add_argument("--packet", required=True)
    for name in ("worktree", "note", "head", "pr", "reason", "question", "recommended", "output", "model"):
        a.add_argument(f"--{name}")
    a.add_argument("--option", action="append"); a.add_argument("--field", action="append", metavar="KEY=VALUE")
    a.set_defaults(fn=cmd_receipt)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    conn = None if args.cmd in WORKER_COMMANDS else store.connect()
    try:
        args.fn(args, conn)
    except (store.StoreError, receipts.ReceiptError, gate.GateError, transport.TransportError) as e:
        print(f"runway-agent: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
