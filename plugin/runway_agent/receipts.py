"""Receipts: typed, append-only lines a worker writes to its local outbox and the controller pulls.

The worker side (`write`, `claim_check`) never touches the database. The controller side
(`apply`) validates each line, dedupes on its id and turns it into an event.
"""

import json
import os
from pathlib import Path

from . import store

# kind -> required fields beyond the common ones. Closing kinds end the attempt.
SCHEMAS = {
    "started": ("worktree",),
    "progress": ("note",),
    "build-done": ("head", "pr"),
    "blocked": ("reason",),
    "needs-you": ("question", "recommended"),
    "failed": ("reason",),
}
CLOSING = ("build-done", "blocked", "needs-you", "failed")
COMMON = ("id", "kind", "dispatch_id", "ticket", "machine", "at")


class ReceiptError(Exception):
    pass


def outbox_dir():
    return store.home() / "outbox"


def machine_label():
    """The label this machine was given at setup, or RUNWAY_MACHINE."""
    if os.environ.get("RUNWAY_MACHINE"):
        return os.environ["RUNWAY_MACHINE"]
    path = store.home() / "machine.json"
    if path.exists():
        return json.loads(path.read_text())["label"]
    raise ReceiptError("this machine has no label: set RUNWAY_MACHINE or run setup")


def load_packet(path):
    return json.loads(Path(path).read_text())


def claim_check(packet):
    """A worker runs this first. The controller claimed; the worker only confirms the claim names it."""
    expected = os.environ.get("RUNWAY_DISPATCH_ID")
    if not expected:
        raise ReceiptError("RUNWAY_DISPATCH_ID is not set: this session was not dispatched, so it must not work the ticket")
    if packet.get("dispatch_id") != expected:
        raise ReceiptError(f"packet is for {packet.get('dispatch_id')}, this session was dispatched as {expected}")
    label = machine_label()
    if packet.get("machine") != label:
        raise ReceiptError(f"packet names machine {packet.get('machine')}, this is {label}")
    return True


def validate(receipt):
    missing = [f for f in COMMON if not receipt.get(f)]
    kind = receipt.get("kind")
    if kind not in SCHEMAS:
        raise ReceiptError(f"unknown receipt kind {kind!r}; one of {', '.join(SCHEMAS)}")
    missing += [f for f in SCHEMAS[kind] if receipt.get(f) in (None, "")]
    if missing:
        raise ReceiptError(f"{kind} receipt is missing {', '.join(missing)}")
    return receipt


def write(packet, kind, **fields):
    """Append one receipt to this dispatch's outbox file. Returns the receipt."""
    receipt = {
        "id": store.new_id("rcpt"),
        "kind": kind,
        "dispatch_id": packet["dispatch_id"],
        "ticket": packet["ticket"],
        "machine": packet["machine"],
        "at": store.now(),
        **{k: v for k, v in fields.items() if v is not None},
    }
    validate(receipt)
    outbox_dir().mkdir(parents=True, exist_ok=True)
    with open(outbox_dir() / f"{packet['dispatch_id']}.jsonl", "a") as f:
        f.write(json.dumps(receipt, sort_keys=True) + "\n")
    return receipt


# --- controller side ---------------------------------------------------------------

def apply(conn, lines, machine_label_seen):
    """Turn pulled outbox lines into events. Returns (added, duplicates, rejected)."""
    added = dup = rejected = 0
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            receipt = validate(json.loads(line))
            with store.tx(conn):
                attempt = conn.execute(
                    "select * from attempts where dispatch_id = ?", (receipt["dispatch_id"],)
                ).fetchone()
                machine = conn.execute("select label from machines where id = ?",
                                       (attempt["machine_id"],)).fetchone() if attempt else None
                if not attempt or machine["label"] != machine_label_seen or receipt["machine"] != machine_label_seen:
                    raise ReceiptError("receipt does not match a dispatch to this machine")
                if conn.execute("select 1 from events where id = ?", (receipt["id"],)).fetchone():
                    dup += 1
                    continue
                if attempt["ended_at"] is not None:
                    # A late line from an attempt already closed (or reaped) is kept for the record only.
                    store.append_event(conn, "late-receipt", attempt["ticket_id"], attempt["id"], receipt,
                                       event_id=receipt["id"], at=receipt["at"])
                    added += 1
                    continue
                kind = receipt["kind"] if receipt["kind"] in CLOSING else f"receipt-{receipt['kind']}"
                store.append_event(conn, kind, attempt["ticket_id"], attempt["id"], receipt,
                                   event_id=receipt["id"], at=receipt["at"])
                if receipt["kind"] in CLOSING:
                    store.end_attempt(conn, attempt, receipt["kind"])
                if receipt["kind"] == "needs-you":
                    store.open_decision(conn, attempt["ticket_id"], receipt["question"],
                                        receipt.get("options") or [], receipt["recommended"], kind="build")
                added += 1
        except (ReceiptError, ValueError, KeyError, TypeError):
            rejected += 1
    return added, dup, rejected


def reap(conn, attempt, herdr_state, grace_passed):
    """Herdr is advisory. A finished or vanished session with no closing receipt becomes a failed attempt."""
    if attempt["ended_at"] is not None:
        return False
    if herdr_state in ("done", "unknown", "gone") and grace_passed:
        with store.tx(conn):
            store.append_event(conn, "failed", attempt["ticket_id"], attempt["id"],
                               {"reason": f"no closing receipt; Herdr says {herdr_state}", "synthetic": True})
            store.end_attempt(conn, attempt, "failed")
            store.open_decision(conn, attempt["ticket_id"],
                                "The session ended without a receipt. Dispatch it again?",
                                ["dispatch again", "drop"], "dispatch again", kind="build")
        return True
    return False
