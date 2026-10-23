"""The review seat: the other model reads the exact head against the ticket's spec and Acceptance.

The controller launches it (`claude -p` or `codex exec`, called directly) and records the verdict
pinned to the commit it read. A reviewer may raise risk, never lower it.
"""

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import store
from .gate import GateError, _run, latest

VERDICTS = ("pass", "fix", "needs-you")
TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "review-prompt.md"
SEATS = {
    "claude": lambda prompt: ["claude", "-p", prompt, "--permission-mode", "plan"],
    "codex": lambda prompt: ["codex", "exec", "--sandbox", "read-only", prompt],
}


def other_model(builder, available):
    """The seat that did not build. One-model fleets fall back to a same-model review."""
    others = [m for m in available if m != builder]
    return (others[0], False) if others else (builder, True)


def prompt(conn, ticket, head, base):
    project = conn.execute("select * from projects where id = ?", (ticket["project_id"],)).fetchone()
    return TEMPLATE.read_text().format(
        ticket=store.ref(conn, ticket), title=ticket["title"], body=ticket["body"] or "(none)",
        spec=ticket["spec_path"] or "(none)", plan=ticket["plan_path"] or "(none)",
        acceptance=ticket["acceptance"] or "(none given)", head=head, base=f"origin/{project['default_branch']}",
        risk=ticket["risk"],
    )


def parse(output):
    """The reviewer ends with one JSON line. Anything unreadable is a needs-you, never a pass."""
    for line in reversed(output.strip().splitlines()):
        line = line.strip().strip("`")
        if line.startswith("{") and '"verdict"' in line:
            try:
                data = json.loads(line)
            except ValueError:
                break
            if data.get("verdict") in VERDICTS:
                return data
            break
    return {"verdict": "needs-you", "findings": ["the reviewer's output had no readable verdict"]}


def record(conn, ticket_ref, verdict, commit, model, findings=(), raise_risk=False, same_model=False):
    if verdict not in VERDICTS:
        raise GateError(f"verdict is one of {', '.join(VERDICTS)}")
    if not re.fullmatch(r"[0-9a-f]{40}", commit or ""):
        raise GateError("a verdict is pinned to a full 40-character commit sha")
    if same_model and verdict == "pass":
        verdict = "needs-you"
        findings = list(findings) + ["same-model review: capped at needs-you"]
    ticket = store.ticket_by_ref(conn, ticket_ref)
    if verdict == "fix" and conn.execute(
            "select 1 from events where ticket_id = ? and kind = 'review-fix'", (ticket["id"],)).fetchone():
        verdict = "needs-you"  # one fix pass, then a person
        findings = list(findings) + ["second fix requested: one fix pass is the limit"]
    with store.tx(conn):
        if raise_risk:
            store.raise_risk(conn, ticket["id"], "; ".join(findings) or "raised by review", by=model)
        store.append_event(conn, f"review-{verdict}", ticket["id"], payload={
            "commit": commit, "model": model, "findings": list(findings), "same_model": same_model})
        if verdict == "fix":
            conn.execute("insert into comments (ticket_id, author, body, created_at) values (?, ?, ?, ?)",
                         (ticket["id"], f"review ({model})",
                          "Fix before merge:\n" + "\n".join(f"- {f}" for f in findings), store.now()))
        if verdict == "needs-you":
            store.open_decision(conn, ticket["id"], f"Review of {commit[:10]} needs you: {'; '.join(findings)[:300]}",
                                ["rework", "drop"], "rework", kind="review")
    return verdict


def run(conn, ticket_ref, available=("claude", "codex"), runner=None):
    """Check out the head in a throwaway worktree, run the other model on it, record the verdict."""
    ticket = store.ticket_by_ref(conn, ticket_ref)
    project = conn.execute("select * from projects where id = ?", (ticket["project_id"],)).fetchone()
    _, built = latest(conn, ticket["id"], ("build-done",))
    if not built.get("head"):
        raise GateError(f"{ticket_ref} has no build-done receipt to review")
    head = built["head"]
    builder = built.get("model") or ticket["model"] or "claude"
    seat, same = other_model(builder, [m for m in available if runner or shutil.which(m)])
    text = prompt(conn, ticket, head, project["default_branch"])
    with tempfile.TemporaryDirectory(prefix="runway-review-") as tmp:
        if runner is None:
            _run(["git", "-C", project["path"], "fetch", "--quiet", "origin", head, project["default_branch"]])
            _run(["git", "-C", project["path"], "worktree", "add", "--detach", tmp, head])
        try:
            if runner:
                output = runner(seat, text, tmp)
            else:
                out = subprocess.run(SEATS[seat](text), cwd=tmp, capture_output=True, text=True, timeout=3600)
                output = out.stdout
        finally:
            if runner is None:
                subprocess.run(["git", "-C", project["path"], "worktree", "remove", "--force", tmp], capture_output=True)
    data = parse(output)
    return record(conn, ticket_ref, data["verdict"], head, seat, data.get("findings", []),
                  raise_risk=data.get("risk") == "not-low", same_model=same)
