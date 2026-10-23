"""The loop's rules against a real SQLite store in a temp home. Run: python3 -m unittest discover -s tests"""

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin"))

from runway_agent import gate, receipts, review, store  # noqa: E402

HEAD = "a" * 40
NEW_HEAD = "b" * 40


class FakeGitHub:
    def __init__(self, head=HEAD, files=("src/app.py",), checks=(("ci", "SUCCESS"),), state="OPEN"):
        self.head, self.files, self.checks_, self.state = head, list(files), list(checks), state
        self.merged = []

    def pr(self, repo, number):
        return {"headRefOid": self.head, "isDraft": True, "state": self.state,
                "files": [{"path": p} for p in self.files], "headRefName": "runway/x", "baseRefName": "main"}

    def checks(self, repo, number):
        return [{"name": n, "state": s} for n, s in self.checks_]

    def ready(self, repo, number):
        pass

    def merge(self, repo, number, head, method):
        if head != self.head:
            raise gate.GateError("head mismatch")
        self.merged.append((number, head, method))
        return {"mergeCommit": {"oid": "c" * 40}}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        os.environ["RUNWAY_AGENT_HOME"] = str(self.home)
        os.environ.pop("RUNWAY_DISPATCH_ID", None)
        os.environ.pop("RUNWAY_MACHINE", None)
        self.conn = store.connect()
        store.add_project(self.conn, "DEMO", "Demo", "example/demo")
        store.add_machine(self.conn, "worker-1", kind="local")

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def low_ticket(self, **kw):
        return store.add_ticket(self.conn, "DEMO", "Add a flag", risk="low", risk_reason="one file, tests only", **kw)

    def as_worker(self, packet):
        os.environ["RUNWAY_DISPATCH_ID"] = packet["dispatch_id"]
        os.environ["RUNWAY_MACHINE"] = packet["machine"]

    def build(self, ticket_ref, head=HEAD, model="claude"):
        packet = store.dispatch(self.conn, ticket_ref, "worker-1")
        self.as_worker(packet)
        receipts.write(packet, "started", worktree="/tmp/w")
        receipts.write(packet, "build-done", head=head, pr=7, model=model)
        lines = (self.home / "outbox" / f"{packet['dispatch_id']}.jsonl").read_text().splitlines()
        receipts.apply(self.conn, lines, "worker-1")
        return packet

    def status(self, ticket_ref):
        return store.ticket_by_ref(self.conn, ticket_ref)["status"]


class Filing(Base):
    def test_a1_add_creates_row_and_filed_event_and_lists(self):
        ref = store.add_ticket(self.conn, "DEMO", "First ticket", spec_path="docs/specs/x.md")
        self.assertEqual(ref, "DEMO-1")
        rows = store.list_tickets(self.conn, "DEMO")
        self.assertEqual([r["title"] for r in rows], ["First ticket"])
        kinds = [e["kind"] for e in store.events_for(self.conn, rows[0]["id"])]
        self.assertEqual(kinds, ["filed"])
        self.assertEqual(rows[0]["risk"], "not-low")

    def test_low_risk_needs_a_reason(self):
        with self.assertRaises(store.StoreError):
            store.add_ticket(self.conn, "DEMO", "x", risk="low")

    def test_numbers_count_per_project(self):
        store.add_ticket(self.conn, "DEMO", "a")
        self.assertEqual(store.add_ticket(self.conn, "DEMO", "b"), "DEMO-2")

    def test_risk_only_goes_up(self):
        ref = self.low_ticket()
        t = store.ticket_by_ref(self.conn, ref)
        with store.tx(self.conn):
            self.assertTrue(store.raise_risk(self.conn, t["id"], "touches auth", "codex"))
            self.assertFalse(store.raise_risk(self.conn, t["id"], "again", "codex"))
        self.assertEqual(store.ticket_by_ref(self.conn, ref)["risk"], "not-low")


class Dispatching(Base):
    def test_a2_concurrent_dispatch_has_one_winner(self):
        ref = self.low_ticket()
        store.add_machine(self.conn, "worker-2", kind="local")
        results, barrier = [], threading.Barrier(2)

        def go(label):
            conn = store.connect()
            barrier.wait()
            try:
                results.append(("ok", store.dispatch(conn, ref, label)["dispatch_id"]))
            except store.StoreError as e:
                results.append(("refused", str(e)))
            finally:
                conn.close()

        threads = [threading.Thread(target=go, args=(m,)) for m in ("worker-1", "worker-2")]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(sorted(r[0] for r in results), ["ok", "refused"])
        live = self.conn.execute("select count(*) from attempts where ended_at is null").fetchone()[0]
        self.assertEqual(live, 1)

    def test_second_dispatch_refused_while_running(self):
        ref = self.low_ticket()
        store.dispatch(self.conn, ref, "worker-1")
        with self.assertRaises(store.StoreError):
            store.dispatch(self.conn, ref, "worker-1")

    def test_blocked_ticket_waits(self):
        first = self.low_ticket()
        second = store.add_ticket(self.conn, "DEMO", "after", blocked_by=[first])
        with self.assertRaisesRegex(store.StoreError, "blocked by DEMO-1"):
            store.dispatch(self.conn, second, "worker-1")

    def test_swarm_is_not_run_in_v1(self):
        ref = store.add_ticket(self.conn, "DEMO", "swarm", strategy="swarm")
        with self.assertRaisesRegex(store.StoreError, "swarm"):
            store.dispatch(self.conn, ref, "worker-1")

    def test_packet_carries_what_the_worker_needs(self):
        ref = store.add_ticket(self.conn, "DEMO", "t", spec_path="docs/specs/s.md", acceptance="- [ ] A1: x")
        p = store.dispatch(self.conn, ref, "worker-1")
        self.assertEqual((p["ticket"], p["branch"], p["spec_path"]), ("DEMO-1", "runway/demo-1", "docs/specs/s.md"))


class Receipts(Base):
    def test_claim_check_refuses_an_undispatched_session(self):
        p = store.dispatch(self.conn, self.low_ticket(), "worker-1")
        with self.assertRaises(receipts.ReceiptError):
            receipts.claim_check(p)
        os.environ["RUNWAY_DISPATCH_ID"] = "dsp_other"
        os.environ["RUNWAY_MACHINE"] = "worker-1"
        with self.assertRaises(receipts.ReceiptError):
            receipts.claim_check(p)
        self.as_worker(p)
        self.assertTrue(receipts.claim_check(p))

    def test_typed_schema(self):
        p = store.dispatch(self.conn, self.low_ticket(), "worker-1")
        with self.assertRaisesRegex(receipts.ReceiptError, "missing head"):
            receipts.write(p, "build-done", pr=3)

    def test_a4_pulling_twice_keeps_one_event_per_receipt(self):
        ref = self.low_ticket()
        p = store.dispatch(self.conn, ref, "worker-1")
        receipts.write(p, "started", worktree="/tmp/w")
        receipts.write(p, "build-done", head=HEAD, pr=7)
        lines = (self.home / "outbox" / f"{p['dispatch_id']}.jsonl").read_text().splitlines()
        self.assertEqual(receipts.apply(self.conn, lines, "worker-1"), (2, 0, 0))
        self.assertEqual(receipts.apply(self.conn, lines, "worker-1"), (0, 2, 0))
        t = store.ticket_by_ref(self.conn, ref)
        kinds = [e["kind"] for e in store.events_for(self.conn, t["id"])]
        self.assertEqual(kinds.count("build-done"), 1)
        self.assertEqual(t["status"], "built")

    def test_receipt_from_the_wrong_machine_is_rejected(self):
        p = store.dispatch(self.conn, self.low_ticket(), "worker-1")
        receipts.write(p, "started", worktree="/tmp/w")
        lines = (self.home / "outbox" / f"{p['dispatch_id']}.jsonl").read_text().splitlines()
        store.add_machine(self.conn, "worker-2", kind="local")
        self.assertEqual(receipts.apply(self.conn, lines, "worker-2"), (0, 0, 1))

    def test_needs_you_opens_a_decision_and_the_answer_requeues(self):
        ref = self.low_ticket()
        p = store.dispatch(self.conn, ref, "worker-1")
        receipts.write(p, "needs-you", question="Keep the old flag?", recommended="yes")
        receipts.apply(self.conn, (self.home / "outbox" / f"{p['dispatch_id']}.jsonl").read_text().splitlines(),
                       "worker-1")
        self.assertEqual(self.status(ref), "needs-you")
        d = store.open_decisions(self.conn)[0]
        store.answer_decision(self.conn, d["id"], "yes", "operator")
        self.assertEqual(self.status(ref), "open")
        self.assertIn("yes", store.dispatch(self.conn, ref, "worker-1")["comments"][0]["body"])

    def test_session_gone_without_receipt_becomes_failed(self):
        ref = self.low_ticket()
        store.dispatch(self.conn, ref, "worker-1")
        attempt = store.live_attempts(self.conn)[0]
        self.assertFalse(receipts.reap(self.conn, attempt, "working", grace_passed=True))
        self.assertTrue(receipts.reap(self.conn, attempt, "done", grace_passed=True))
        self.assertEqual(self.status(ref), "failed")
        self.assertEqual(store.live_attempts(self.conn), [])
        self.assertTrue(store.dispatch(self.conn, ref, "worker-1"))  # offered again


class Reviewing(Base):
    def test_other_model_reviews(self):
        self.assertEqual(review.other_model("claude", ["claude", "codex"]), ("codex", False))
        self.assertEqual(review.other_model("claude", ["claude"]), ("claude", True))

    def test_run_records_verdict_pinned_to_the_head(self):
        ref = self.low_ticket()
        self.build(ref, model="claude")
        seen = {}

        def runner(seat, text, cwd):
            seen["seat"] = seat
            return 'looks fine\n{"verdict": "pass", "risk": "low", "findings": []}'

        self.assertEqual(review.run(self.conn, ref, runner=runner), "pass")
        self.assertEqual(seen["seat"], "codex")
        _, ev = gate.latest(self.conn, store.ticket_by_ref(self.conn, ref)["id"], ("review-pass",))
        self.assertEqual(ev["commit"], HEAD)

    def test_unreadable_output_is_never_a_pass(self):
        self.assertEqual(review.parse("I think it's good")["verdict"], "needs-you")

    def test_reviewer_raises_risk(self):
        ref = self.low_ticket()
        self.build(ref)
        review.run(self.conn, ref, runner=lambda *a: '{"verdict": "pass", "risk": "not-low", "findings": ["auth"]}')
        self.assertEqual(store.ticket_by_ref(self.conn, ref)["risk"], "not-low")

    def test_one_fix_pass_then_a_person(self):
        ref = self.low_ticket()
        self.build(ref)
        self.assertEqual(review.record(self.conn, ref, "fix", HEAD, "codex", ["a.py: x"]), "fix")
        self.assertEqual(self.status(ref), "fix")
        self.build(ref, head=NEW_HEAD)  # the fix pass is dispatched like any ticket
        self.assertEqual(review.record(self.conn, ref, "fix", NEW_HEAD, "codex", ["a.py: y"]), "needs-you")

    def test_same_model_pass_is_capped(self):
        ref = self.low_ticket()
        self.build(ref)
        self.assertEqual(review.record(self.conn, ref, "pass", HEAD, "claude", same_model=True), "needs-you")


class Gating(Base):
    def reviewed(self, head=HEAD, **kw):
        ref = self.low_ticket(**kw)
        self.build(ref, head=head)
        review.record(self.conn, ref, "pass", head, "codex")
        return ref

    def test_low_risk_reviewed_green_merges_with_expected_head(self):
        ref = self.reviewed()
        gh = FakeGitHub()
        result = gate.run(self.conn, ref, gh=gh, config={})
        self.assertEqual(result["verdict"], "merge", result["reasons"])
        self.assertEqual(gh.merged, [(7, HEAD, "squash")])
        self.assertEqual(self.status(ref), "done")

    def test_head_moved_after_review_stops(self):
        ref = self.reviewed()
        gh = FakeGitHub(head=NEW_HEAD)
        result = gate.run(self.conn, ref, gh=gh, config={})
        self.assertEqual(result["verdict"], "needs-you")
        self.assertEqual(gh.merged, [])
        self.assertEqual(self.status(ref), "needs-you")

    def test_sensitive_paths_never_auto_merge(self):
        for path in ("runway.json", ".github/workflows/ci.yml", "db/migrations/001.sql", "src/auth/login.py"):
            with self.subTest(path=path):
                self.assertTrue(gate.sensitive_hits([path], gate.DEFAULT_SENSITIVE))
        ref = self.reviewed()
        result = gate.run(self.conn, ref, gh=FakeGitHub(files=["runway.json"]), config={}, dry_run=True)
        self.assertIn("sensitive", " ".join(result["reasons"]))

    def test_repo_sensitive_list_comes_from_config(self):
        ref = self.reviewed()
        result = gate.evaluate(self.conn, ref, gh=FakeGitHub(files=["infra/main.tf"]),
                               config={"sensitive_paths": ["infra/**"]})
        self.assertEqual(result["verdict"], "needs-you")

    def test_not_low_risk_stops(self):
        ref = store.add_ticket(self.conn, "DEMO", "risky")
        self.build(ref)
        review.record(self.conn, ref, "pass", HEAD, "codex")
        self.assertIn("risk is not-low", gate.evaluate(self.conn, ref, gh=FakeGitHub(), config={})["reasons"])

    def test_red_or_missing_checks_stop(self):
        ref = self.reviewed()
        red = gate.evaluate(self.conn, ref, gh=FakeGitHub(checks=[("ci", "FAILURE")]), config={})
        self.assertEqual(red["verdict"], "needs-you")
        none = gate.evaluate(self.conn, ref, gh=FakeGitHub(checks=[]), config={})
        self.assertIn("no CI", " ".join(none["reasons"]))
        own = gate.evaluate(self.conn, ref, gh=FakeGitHub(checks=[]), config={"check_cmd": "true"},
                            own_check=lambda project, head, cmd: (head == HEAD, ""))
        self.assertEqual(own["verdict"], "merge")

    def test_operator_approval_only_merges_the_head_they_saw(self):
        ref = store.add_ticket(self.conn, "DEMO", "risky")
        self.build(ref)
        review.record(self.conn, ref, "pass", HEAD, "codex")
        gh = FakeGitHub()
        gate.run(self.conn, ref, gh=gh, config={})
        gh.head = NEW_HEAD
        with self.assertRaisesRegex(gate.GateError, "head moved"):
            gate.approve(self.conn, ref, "operator", gh=gh)
        gh.head = HEAD
        gate.approve(self.conn, ref, "operator", gh=gh)
        self.assertEqual(self.status(ref), "done")


class Cli(Base):
    """The wrapper end to end on a local machine: file, dispatch, worker receipts, pull, list."""

    def run_cli(self, *args, env=None):
        out = subprocess.run([str(ROOT / "plugin" / "bin" / "runway-agent"), *args], capture_output=True,
                             text=True, env={**os.environ, **(env or {})})
        self.assertEqual(out.returncode, 0, out.stderr)
        return out.stdout

    def test_loop_through_the_cli(self):
        ref = self.run_cli("ticket", "add", "DEMO", "--title", "Via CLI", "--risk", "low",
                           "--risk-reason", "docs only").strip()
        packet = json.loads(self.run_cli("dispatch", ref, "--machine", "worker-1"))
        path = self.home / "packet.json"
        path.write_text(json.dumps(packet))
        env = {"RUNWAY_DISPATCH_ID": packet["dispatch_id"], "RUNWAY_MACHINE": "worker-1"}
        self.run_cli("claim-check", "--packet", str(path), env=env)
        self.run_cli("receipt", "build-done", "--packet", str(path), "--head", HEAD, "--pr", "#9", env=env)
        self.assertIn("1 new", self.run_cli("pull", "--machine", "worker-1"))
        self.assertIn("0 new, 1 already had", self.run_cli("pull", "--machine", "worker-1"))
        self.assertIn("built", self.run_cli("ticket", "list"))


if __name__ == "__main__":
    unittest.main()
