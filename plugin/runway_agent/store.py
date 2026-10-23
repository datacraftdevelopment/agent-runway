"""The controller's SQLite store: the ticket tracker and the only authority on run state.

Every change is an append-only row in `events`; `tickets.status` is a cache that only
`append_event` writes. See docs/specs/2026-10-23-controller-database-design.md.
"""

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

RISKS = ("low", "not-low")
OPEN_STATUSES = ("open", "failed", "fix")  # a ticket in one of these can be dispatched

SCHEMA = """
create table if not exists projects (
  id             integer primary key,
  key            text not null unique,
  name           text not null,
  repo           text not null,            -- owner/name on GitHub
  path           text,                     -- the controller's clone, for reading the default branch
  default_branch text not null default 'main'
);

create table if not exists tickets (
  id          integer primary key,
  project_id  integer not null references projects(id),
  number      integer not null,
  title       text not null,
  body        text not null default '',
  risk        text not null default 'not-low' check (risk in ('low', 'not-low')),
  risk_reason text,
  status      text not null default 'open',
  strategy    text not null default 'single' check (strategy in ('single', 'swarm')),
  spec_path   text,
  plan_path   text,
  acceptance  text not null default '',    -- the Acceptance lines this ticket must satisfy
  touches     text not null default '',    -- expected paths, one per line
  model       text,                        -- builder model when it matters: claude or codex
  created_at  text not null,
  unique (project_id, number)
);

create table if not exists ticket_blocks (
  ticket_id     integer not null references tickets(id),
  blocked_by_id integer not null references tickets(id),
  primary key (ticket_id, blocked_by_id)
);

create table if not exists comments (
  id         integer primary key,
  ticket_id  integer not null references tickets(id),
  author     text not null,
  body       text not null,
  created_at text not null
);

create table if not exists machines (
  id          integer primary key,
  label       text not null unique,
  herdr_label text,
  ssh_host    text,                         -- null for the controller itself
  kind        text not null default 'ssh' check (kind in ('local', 'ssh', 'cloud')),
  enabled     integer not null default 1
);

create table if not exists attempts (
  id            integer primary key,
  ticket_id     integer not null references tickets(id),
  dispatch_id   text not null unique,
  machine_id    integer not null references machines(id),
  herdr_session text,
  branch        text not null,
  started_at    text not null,
  ended_at      text,
  outcome       text
);
-- The claim: at most one live attempt per ticket, enforced by the database.
create unique index if not exists one_live_attempt on attempts(ticket_id) where ended_at is null;

create table if not exists events (
  id         text primary key,              -- receipts carry their own id, so a replay is ignored
  at         text not null,
  kind       text not null,
  ticket_id  integer references tickets(id),
  attempt_id integer references attempts(id),
  payload    text not null default '{}'
);

-- Steered sessions, found by scanning each machine's Claude Code and Codex session logs (spec: Steered sessions).
create table if not exists sessions (
  id           integer primary key,
  machine_id   integer not null references machines(id),
  agent        text not null check (agent in ('claude', 'codex')),
  session_id   text not null,
  folder       text,
  started_at   text,
  last_seen_at text,
  source       text not null default 'scan',
  unique (machine_id, agent, session_id)
);

create table if not exists decisions (
  id          integer primary key,
  ticket_id   integer not null references tickets(id),
  kind        text not null default 'build' check (kind in ('build', 'review', 'gate')),
  question    text not null,
  options     text not null default '[]',
  recommended text,
  answer      text,
  answered_by text,
  answered_at text,
  revision    integer not null default 1
);
"""

# What each event kind does to the ticket's status. Kinds not listed leave it alone.
STATUS_AFTER = {
    "filed": "open",
    "dispatched": "running",
    "build-done": "built",
    "blocked": "blocked",
    "needs-you": "needs-you",
    "failed": "failed",
    "review-pass": "reviewed",
    "review-fix": "fix",
    "review-needs-you": "needs-you",
    "gate-needs-you": "needs-you",
    "merged": "done",
    "dropped": "dropped",
    "reopened": "open",
}


class StoreError(Exception):
    pass


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_id(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def home():
    return Path(os.environ.get("RUNWAY_AGENT_HOME", Path.home() / ".runway-agent"))


def connect(path=None):
    path = Path(path) if path else home() / "runway.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), isolation_level=None, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("pragma foreign_keys = on")
    conn.execute("pragma journal_mode = wal")
    conn.executescript(SCHEMA)
    return conn


class tx:
    """BEGIN IMMEDIATE so two writers serialize instead of both reading stale state."""

    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        self.conn.execute("begin immediate")
        return self.conn

    def __exit__(self, exc_type, *_):
        self.conn.execute("rollback" if exc_type else "commit")
        return False


def append_event(conn, kind, ticket_id=None, attempt_id=None, payload=None, event_id=None, at=None):
    """Insert one event; returns False when that id is already there (a replayed receipt)."""
    event_id = event_id or new_id("ev")
    cur = conn.execute(
        "insert or ignore into events (id, at, kind, ticket_id, attempt_id, payload) values (?, ?, ?, ?, ?, ?)",
        (event_id, at or now(), kind, ticket_id, attempt_id, json.dumps(payload or {}, sort_keys=True)),
    )
    if cur.rowcount == 0:
        return False
    status = STATUS_AFTER.get(kind)
    if status and ticket_id is not None:
        conn.execute("update tickets set status = ? where id = ?", (status, ticket_id))
    return True


# --- projects and machines ---------------------------------------------------

def add_project(conn, key, name, repo, path=None, default_branch="main"):
    with tx(conn):
        cur = conn.execute(
            "insert into projects (key, name, repo, path, default_branch) values (?, ?, ?, ?, ?)",
            (key, name, repo, path, default_branch),
        )
        append_event(conn, "project-added", payload={"key": key, "repo": repo})
    return cur.lastrowid


def project_by_key(conn, key):
    row = conn.execute("select * from projects where key = ?", (key,)).fetchone()
    if not row:
        raise StoreError(f"no project {key}")
    return row


def add_machine(conn, label, kind="ssh", ssh_host=None, herdr_label=None):
    with tx(conn):
        conn.execute(
            "insert into machines (label, herdr_label, ssh_host, kind) values (?, ?, ?, ?)",
            (label, herdr_label or label, ssh_host, kind),
        )
        append_event(conn, "machine-added", payload={"label": label, "kind": kind})


def machine_by_label(conn, label):
    row = conn.execute("select * from machines where label = ?", (label,)).fetchone()
    if not row:
        raise StoreError(f"no machine {label}")
    return row


# --- tickets -------------------------------------------------------------------

def ref(conn, ticket):
    key = conn.execute("select key from projects where id = ?", (ticket["project_id"],)).fetchone()["key"]
    return f"{key}-{ticket['number']}"


def ticket_by_ref(conn, ticket_ref):
    key, _, num = ticket_ref.rpartition("-")
    if not key or not num.isdigit():
        raise StoreError(f"ticket refs look like KEY-12, not {ticket_ref}")
    row = conn.execute(
        "select t.* from tickets t join projects p on p.id = t.project_id where p.key = ? and t.number = ?",
        (key, int(num)),
    ).fetchone()
    if not row:
        raise StoreError(f"no ticket {ticket_ref}")
    return row


def add_ticket(conn, project_key, title, body="", risk="not-low", risk_reason=None, strategy="single",
               spec_path=None, plan_path=None, acceptance="", touches="", model=None, blocked_by=()):
    if risk not in RISKS:
        raise StoreError(f"risk is low or not-low, not {risk}")
    if risk == "low" and not (risk_reason or "").strip():
        raise StoreError("a low-risk ticket needs --risk-reason")
    with tx(conn):
        project = project_by_key(conn, project_key)
        number = conn.execute(
            "select coalesce(max(number), 0) + 1 from tickets where project_id = ?", (project["id"],)
        ).fetchone()[0]
        cur = conn.execute(
            """insert into tickets (project_id, number, title, body, risk, risk_reason, strategy, spec_path,
               plan_path, acceptance, touches, model, created_at) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (project["id"], number, title, body, risk, risk_reason, strategy, spec_path, plan_path,
             acceptance, touches, model, now()),
        )
        ticket_id = cur.lastrowid
        for blocker in blocked_by:
            b = ticket_by_ref(conn, blocker)
            conn.execute("insert into ticket_blocks (ticket_id, blocked_by_id) values (?, ?)", (ticket_id, b["id"]))
        append_event(conn, "filed", ticket_id, payload={"risk": risk, "risk_reason": risk_reason})
    return f"{project_key}-{number}"


def raise_risk(conn, ticket_id, reason, by):
    """Risk only goes up. Raising a not-low ticket is a no-op."""
    row = conn.execute("select risk from tickets where id = ?", (ticket_id,)).fetchone()
    if row["risk"] == "not-low":
        return False
    conn.execute("update tickets set risk = 'not-low' where id = ?", (ticket_id,))
    append_event(conn, "risk-raised", ticket_id, payload={"reason": reason, "by": by})
    return True


def blockers_open(conn, ticket_id):
    rows = conn.execute(
        """select t.* from ticket_blocks b join tickets t on t.id = b.blocked_by_id
           where b.ticket_id = ? and t.status not in ('done', 'dropped')""",
        (ticket_id,),
    ).fetchall()
    return [ref(conn, r) for r in rows]


def add_comment(conn, ticket_id, author, body):
    with tx(conn):
        conn.execute(
            "insert into comments (ticket_id, author, body, created_at) values (?, ?, ?, ?)",
            (ticket_id, author, body, now()),
        )
        append_event(conn, "comment", ticket_id, payload={"author": author})


def list_tickets(conn, project_key=None, status=None):
    sql = "select t.*, p.key from tickets t join projects p on p.id = t.project_id where 1=1"
    args = []
    if project_key:
        sql += " and p.key = ?"
        args.append(project_key)
    if status:
        sql += " and t.status = ?"
        args.append(status)
    order = "case t.status when 'needs-you' then 0 when 'running' then 1 else 2 end, p.key, t.number"
    return conn.execute(sql + " order by " + order, args).fetchall()


def events_for(conn, ticket_id):
    return conn.execute("select * from events where ticket_id = ? order by at, rowid", (ticket_id,)).fetchall()


# --- dispatch (the claim) --------------------------------------------------------

def dispatch(conn, ticket_ref, machine_label):
    """Claim a ticket for one machine. Exactly one concurrent caller wins; the rest get StoreError."""
    try:
        with tx(conn):
            ticket = ticket_by_ref(conn, ticket_ref)
            machine = machine_by_label(conn, machine_label)
            if not machine["enabled"]:
                raise StoreError(f"machine {machine_label} is disabled")
            if ticket["status"] not in OPEN_STATUSES:
                raise StoreError(f"{ticket_ref} is {ticket['status']}, not ready to dispatch")
            if ticket["strategy"] == "swarm":
                raise StoreError(f"{ticket_ref} asks for a swarm, which v1 does not run")
            waiting = blockers_open(conn, ticket["id"])
            if waiting:
                raise StoreError(f"{ticket_ref} is blocked by {', '.join(waiting)}")
            dispatch_id = new_id("dsp")
            branch = f"runway/{ticket_ref.lower()}"
            cur = conn.execute(
                "insert into attempts (ticket_id, dispatch_id, machine_id, branch, started_at) values (?, ?, ?, ?, ?)",
                (ticket["id"], dispatch_id, machine["id"], branch, now()),
            )
            append_event(conn, "dispatched", ticket["id"], cur.lastrowid,
                         {"dispatch_id": dispatch_id, "machine": machine_label})
    except sqlite3.IntegrityError:
        raise StoreError(f"{ticket_ref} already has a live attempt")
    return packet(conn, dispatch_id)


def attempt_by_dispatch(conn, dispatch_id):
    row = conn.execute("select * from attempts where dispatch_id = ?", (dispatch_id,)).fetchone()
    if not row:
        raise StoreError(f"no attempt {dispatch_id}")
    return row


def packet(conn, dispatch_id):
    """Everything a worker gets. Workers never read the database."""
    attempt = attempt_by_dispatch(conn, dispatch_id)
    ticket = conn.execute("select * from tickets where id = ?", (attempt["ticket_id"],)).fetchone()
    project = conn.execute("select * from projects where id = ?", (ticket["project_id"],)).fetchone()
    machine = conn.execute("select * from machines where id = ?", (attempt["machine_id"],)).fetchone()
    comments = conn.execute(
        "select author, body, created_at from comments where ticket_id = ? order by id", (ticket["id"],)
    ).fetchall()
    return {
        "dispatch_id": dispatch_id,
        "ticket": ref(conn, ticket),
        "machine": machine["label"],
        "repo": project["repo"],
        "default_branch": project["default_branch"],
        "branch": attempt["branch"],
        "title": ticket["title"],
        "body": ticket["body"],
        "spec_path": ticket["spec_path"],
        "plan_path": ticket["plan_path"],
        "acceptance": ticket["acceptance"],
        "touches": ticket["touches"],
        "comments": [dict(c) for c in comments],
    }


def set_herdr_session(conn, dispatch_id, session):
    with tx(conn):
        attempt = attempt_by_dispatch(conn, dispatch_id)
        conn.execute("update attempts set herdr_session = ? where id = ?", (session, attempt["id"]))
        append_event(conn, "launched", attempt["ticket_id"], attempt["id"], {"herdr_session": session})


def end_attempt(conn, attempt, outcome):
    conn.execute("update attempts set ended_at = ?, outcome = ? where id = ? and ended_at is null",
                 (now(), outcome, attempt["id"]))


def live_attempts(conn):
    return conn.execute("select * from attempts where ended_at is null order by id").fetchall()


# --- decisions -------------------------------------------------------------------

def open_decision(conn, ticket_id, question, options=(), recommended=None, kind="build"):
    cur = conn.execute(
        "insert into decisions (ticket_id, kind, question, options, recommended) values (?, ?, ?, ?, ?)",
        (ticket_id, kind, question, json.dumps(list(options)), recommended),
    )
    return cur.lastrowid


def answer_decision(conn, decision_id, answer, by):
    """The controller is the one writer. A worker never answers its own needs-you."""
    with tx(conn):
        row = conn.execute("select * from decisions where id = ?", (decision_id,)).fetchone()
        if not row:
            raise StoreError(f"no decision {decision_id}")
        conn.execute(
            "update decisions set answer = ?, answered_by = ?, answered_at = ?, revision = revision + 1 where id = ?",
            (answer, by, now(), decision_id),
        )
        conn.execute("insert into comments (ticket_id, author, body, created_at) values (?, ?, ?, ?)",
                     (row["ticket_id"], by, f"Answer to \"{row['question']}\": {answer}", now()))
        append_event(conn, "answered", row["ticket_id"], payload={"decision": decision_id, "answer": answer, "by": by})
        ticket = conn.execute("select status from tickets where id = ?", (row["ticket_id"],)).fetchone()
        # A build or review question answered sends the ticket back to the queue with the answer in its
        # comments. A gate question is about the PR itself; the CLI acts on that answer.
        if ticket["status"] == "needs-you" and row["kind"] != "gate":
            append_event(conn, "reopened", row["ticket_id"], payload={"after_decision": decision_id})
    return conn.execute("select * from decisions where id = ?", (decision_id,)).fetchone()


def open_decisions(conn):
    return conn.execute("select * from decisions where answer is null order by id").fetchall()
