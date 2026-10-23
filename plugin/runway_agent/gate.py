"""The merge gate, as code. It trusts nothing the builder can edit.

Inputs: risk from the controller's store (set at filing, raised by review), the review verdict
pinned to a commit, the PR's head and changed paths from GitHub, checks from CI on that head
(or a check the gate runs itself), and runway.json read from the default branch.
"""

import fnmatch
import json
import subprocess
import tempfile

from . import store

DEFAULT_SENSITIVE = (
    "runway.json",
    ".github/**",
    "**/auth/**", "**/*auth*",
    "**/payment*/**", "**/*payment*", "**/billing/**",
    "**/migrations/**", "supabase/**", "**/*.sql",
    ".gitlab-ci.yml", ".circleci/**", "Jenkinsfile", "**/Dockerfile",
)
CI_GREEN = ("SUCCESS", "SKIPPED", "NEUTRAL")


class GateError(Exception):
    pass


def _run(args, cwd=None):
    out = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if out.returncode != 0:
        raise GateError(f"{' '.join(args[:3])} failed: {out.stderr.strip() or out.stdout.strip()}")
    return out.stdout


class GitHub:
    """The few gh calls the gate makes. Tests swap in a fake."""

    def pr(self, repo, number):
        return json.loads(_run(["gh", "pr", "view", str(number), "--repo", repo, "--json",
                                "headRefOid,isDraft,state,files,headRefName,baseRefName"]))

    def checks(self, repo, number):
        out = subprocess.run(["gh", "pr", "checks", str(number), "--repo", repo, "--json", "name,state"],
                             capture_output=True, text=True)
        if out.returncode not in (0, 8) or not out.stdout.strip():  # 8 = checks pending
            return []
        return json.loads(out.stdout)

    def ready(self, repo, number):
        _run(["gh", "pr", "ready", str(number), "--repo", repo])

    def merge(self, repo, number, head, method):
        _run(["gh", "pr", "merge", str(number), "--repo", repo, f"--{method}", "--match-head-commit", head])
        return json.loads(_run(["gh", "pr", "view", str(number), "--repo", repo, "--json", "mergeCommit"]))


def default_branch_config(project):
    """runway.json as the default branch has it, never as the PR branch has it."""
    if not project["path"]:
        raise GateError(f"project {project['key']} has no controller clone path; the gate reads runway.json from it")
    _run(["git", "-C", project["path"], "fetch", "--quiet", "origin", project["default_branch"]])
    out = subprocess.run(["git", "-C", project["path"], "show", f"origin/{project['default_branch']}:runway.json"],
                         capture_output=True, text=True)
    return json.loads(out.stdout) if out.returncode == 0 and out.stdout.strip() else {}


def run_own_check(project, head, check_cmd):
    """Run the repo's check at the exact head in a throwaway worktree. Returns (ok, tail of output)."""
    with tempfile.TemporaryDirectory(prefix="runway-gate-") as tmp:
        _run(["git", "-C", project["path"], "fetch", "--quiet", "origin", head])
        _run(["git", "-C", project["path"], "worktree", "add", "--detach", tmp, head])
        try:
            out = subprocess.run(check_cmd, shell=True, cwd=tmp, capture_output=True, text=True)
            return out.returncode == 0, (out.stdout + out.stderr)[-2000:]
        finally:
            subprocess.run(["git", "-C", project["path"], "worktree", "remove", "--force", tmp], capture_output=True)


def sensitive_hits(paths, patterns):
    return sorted({p for p in paths for pat in patterns
                   if fnmatch.fnmatch(p, pat) or fnmatch.fnmatch(p, pat.replace("**/", ""))})


def latest(conn, ticket_id, kinds):
    marks = ",".join("?" * len(kinds))
    row = conn.execute(f"select * from events where ticket_id = ? and kind in ({marks}) order by at desc, rowid desc limit 1",
                       (ticket_id, *kinds)).fetchone()
    return (row, json.loads(row["payload"])) if row else (None, {})


def evaluate(conn, ticket_ref, gh=None, config=None, own_check=None):
    """Decide without acting. Returns a dict: verdict ('merge' or 'needs-you'), reasons, head, pr."""
    gh = gh or GitHub()
    ticket = store.ticket_by_ref(conn, ticket_ref)
    project = conn.execute("select * from projects where id = ?", (ticket["project_id"],)).fetchone()
    _, built = latest(conn, ticket["id"], ("build-done",))
    if not built.get("pr"):
        raise GateError(f"{ticket_ref} has no build-done receipt with a PR")
    pr_number = built["pr"]
    pr = gh.pr(project["repo"], pr_number)
    head = pr["headRefOid"]
    config = config if config is not None else default_branch_config(project)
    reasons = []

    if pr["state"] != "OPEN":
        reasons.append(f"PR #{pr_number} is {pr['state'].lower()}")
    if ticket["risk"] != "low":
        reasons.append("risk is not-low")
    review_ev, review = latest(conn, ticket["id"], ("review-pass", "review-fix", "review-needs-you"))
    if not review_ev or review_ev["kind"] != "review-pass":
        reasons.append("no passing review")
    elif review.get("commit") != head:
        reasons.append(f"review passed {str(review.get('commit'))[:10]}, but the head is now {head[:10]}")
    elif review.get("same_model"):
        reasons.append("reviewed by the same model that built it")

    checks = gh.checks(project["repo"], pr_number)
    if checks:
        red = [c["name"] for c in checks if c["state"] not in CI_GREEN]
        if red:
            reasons.append(f"checks not green: {', '.join(red)}")
    elif config.get("check_cmd") and own_check is not False:
        ok, tail = (own_check or run_own_check)(project, head, config["check_cmd"])
        if not ok:
            reasons.append("the gate's own check run failed")
    else:
        reasons.append("no CI on the head and no check_cmd in runway.json")

    patterns = list(DEFAULT_SENSITIVE) + list(config.get("sensitive_paths", []))
    hits = sensitive_hits([f["path"] for f in pr.get("files", [])], patterns)
    if hits:
        reasons.append(f"touches sensitive paths: {', '.join(hits[:5])}")

    return {"verdict": "needs-you" if reasons else "merge", "reasons": reasons, "head": head,
            "pr": pr_number, "repo": project["repo"], "method": config.get("merge_method", "squash")}


def run(conn, ticket_ref, gh=None, config=None, own_check=None, dry_run=False):
    gh = gh or GitHub()
    result = evaluate(conn, ticket_ref, gh, config, own_check)
    if dry_run:
        return result
    ticket = store.ticket_by_ref(conn, ticket_ref)
    if result["verdict"] == "merge":
        merge(conn, ticket, result, gh, by="gate")
    else:
        with store.tx(conn):
            store.append_event(conn, "gate-needs-you", ticket["id"], payload=result)
            result["decision"] = store.open_decision(
                conn, ticket["id"], f"PR #{result['pr']} stopped at the gate: {'; '.join(result['reasons'])}. Merge it?",
                ["merge", "rework", "drop"], None, kind="gate")
    return result


def merge(conn, ticket, result, gh, by):
    gh.ready(result["repo"], result["pr"])
    merged = gh.merge(result["repo"], result["pr"], result["head"], result["method"])
    with store.tx(conn):
        store.append_event(conn, "merged", ticket["id"], payload={
            "pr": result["pr"], "head": result["head"], "by": by,
            "merge_commit": (merged.get("mergeCommit") or {}).get("oid")})


def approve(conn, ticket_ref, by, gh=None):
    """The operator said merge. Only the head they were shown can merge."""
    gh = gh or GitHub()
    ticket = store.ticket_by_ref(conn, ticket_ref)
    _, stopped = latest(conn, ticket["id"], ("gate-needs-you",))
    if not stopped:
        raise GateError(f"{ticket_ref} has no gate stop to approve")
    current = gh.pr(stopped["repo"], stopped["pr"])["headRefOid"]
    if current != stopped["head"]:
        raise GateError(f"the head moved from {stopped['head'][:10]} to {current[:10]} since the gate stopped; run the gate again")
    merge(conn, ticket, stopped, gh, by=by)
    return stopped
