"""The one local database: ~/.runway/runway.db (or $RUNWAY_HOME/runway.db).

Everything Runway knows lives here: repos, runners, agents, tickets and what blocks them, runs, reviews, answers and
the event log. The app, the loop, the skills and a terminal all read and write it through this module. Stdlib only.
"""

import json
import os
import sqlite3
import time
from pathlib import Path

SCHEMA_VERSION = 9

MIGRATIONS = {
    1: """
    CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
    CREATE TABLE repos (
        name TEXT PRIMARY KEY,
        path TEXT NOT NULL,              -- the local clone on the repo's main computer
        slug TEXT,                       -- owner/name on GitHub
        base TEXT NOT NULL DEFAULT 'main',
        main_computer TEXT NOT NULL DEFAULT 'This Mac',
        runs_on TEXT NOT NULL DEFAULT 'any' CHECK (runs_on IN ('any', 'main')),
        active INTEGER NOT NULL DEFAULT 1, -- Start/Stop: stopped means nothing new starts for this repo
        paused_until REAL
    );
    CREATE TABLE runners (
        name TEXT PRIMARY KEY,
        kind TEXT NOT NULL CHECK (kind IN ('this_mac', 'ssh_mac', 'cloud')),
        host TEXT,
        slots INTEGER NOT NULL DEFAULT 2,
        state TEXT NOT NULL DEFAULT 'online' CHECK (state IN ('online', 'asleep', 'offline')),
        paused_until REAL
    );
    CREATE TABLE agents (
        kind TEXT PRIMARY KEY CHECK (kind IN ('claude', 'codex')),
        signed_in INTEGER NOT NULL DEFAULT 1,
        resting_until REAL,
        reason TEXT
    );
    CREATE TABLE tickets (
        id TEXT PRIMARY KEY,
        repo TEXT NOT NULL REFERENCES repos(name),
        base TEXT NOT NULL,
        title TEXT NOT NULL,
        body TEXT NOT NULL DEFAULT '',
        acceptance TEXT NOT NULL DEFAULT '[]',   -- JSON list of Acceptance lines
        touches TEXT NOT NULL DEFAULT '[]',      -- JSON list
        risk TEXT NOT NULL DEFAULT 'not_low' CHECK (risk IN ('low', 'not_low')),
        risk_reason TEXT,
        agent TEXT NOT NULL DEFAULT 'any' CHECK (agent IN ('any', 'claude', 'codex')),
        runs_on TEXT,                            -- a runner name; NULL: any free runner
        pinned INTEGER NOT NULL DEFAULT 0,
        state TEXT NOT NULL DEFAULT 'queued',
        stage TEXT,
        branch TEXT,
        pr INTEGER,
        sha TEXT,
        review TEXT,
        question TEXT,                           -- JSON {text, short, go_label, no_label, kind}
        note TEXT,                               -- carried into the next run: the person's answer or a fix note
        fix_passes INTEGER NOT NULL DEFAULT 0,
        filed_from TEXT NOT NULL DEFAULT 'a terminal',
        filed_at REAL NOT NULL,
        updated_at REAL NOT NULL
    );
    CREATE TABLE blockers (
        ticket TEXT NOT NULL REFERENCES tickets(id),
        blocked_by TEXT NOT NULL,
        PRIMARY KEY (ticket, blocked_by)
    );
    CREATE TABLE runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticket TEXT NOT NULL REFERENCES tickets(id),
        kind TEXT NOT NULL CHECK (kind IN ('build', 'review')),
        agent TEXT NOT NULL,
        runner TEXT NOT NULL,
        dir TEXT,                                -- the worktree
        tmux TEXT,                               -- the tmux session name
        session_id TEXT,                         -- for claude --resume / codex resume
        sha TEXT,                                -- the commit a review is pinned to
        started_at REAL NOT NULL,
        ended_at REAL,
        outcome TEXT                             -- done, blocked, needs_you, failed, limited, pass, fail
    );
    CREATE TABLE answers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticket TEXT NOT NULL,
        answer TEXT NOT NULL CHECK (answer IN ('go', 'no')),
        note TEXT,
        at REAL NOT NULL
    );
    CREATE TABLE events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        at REAL NOT NULL,
        kind TEXT NOT NULL,
        repo TEXT,
        ticket TEXT,
        text TEXT NOT NULL
    );
    CREATE TABLE setup (
        runner TEXT PRIMARY KEY,
        reachable TEXT NOT NULL DEFAULT 'checking',
        claude TEXT NOT NULL DEFAULT 'checking',
        codex TEXT NOT NULL DEFAULT 'checking',
        github TEXT NOT NULL DEFAULT 'checking',
        at REAL
    );
    """,
    # The check command first run asks for, used when the repo has no runway.json saying one.
    2: """
    ALTER TABLE repos ADD COLUMN check_cmd TEXT;
    """,
    # Review is two fresh sessions (Joe, 2026-10-25): a code review and a function review, each its own run.
    3: """
    ALTER TABLE runs ADD COLUMN role TEXT;
    ALTER TABLE tickets ADD COLUMN function_review TEXT;
    UPDATE runs SET role = 'code' WHERE kind = 'review';
    """,
    # Hands-off features (Joe, 2026-10-25): what each run cost, when and by whom a ticket merged, take backs, and
    # every stop that needed the person, with its reason.
    4: """
    ALTER TABLE runs ADD COLUMN tokens_in INTEGER;
    ALTER TABLE runs ADD COLUMN tokens_out INTEGER;
    ALTER TABLE runs ADD COLUMN cost_usd REAL;
    ALTER TABLE runs ADD COLUMN base_sha TEXT;
    ALTER TABLE tickets ADD COLUMN merged_at REAL;
    ALTER TABLE tickets ADD COLUMN merged_by TEXT;
    ALTER TABLE tickets ADD COLUMN taken INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE tickets ADD COLUMN take_dir TEXT;
    ALTER TABLE tickets ADD COLUMN kind TEXT NOT NULL DEFAULT 'work';
    CREATE TABLE stops (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticket TEXT NOT NULL,
        repo TEXT NOT NULL,
        at REAL NOT NULL,
        reason TEXT NOT NULL,
        run INTEGER,
        detail TEXT
    );
    """,
    # Take back (Joe, 2026-10-25): every run keeps enough for a new session to read what it did: its folder
    # (~/.runway/runs/<ticket>/<n>/), branch, the last stage it reached and a link to its transcript.
    5: """
    ALTER TABLE runs ADD COLUMN run_dir TEXT;
    ALTER TABLE runs ADD COLUMN branch TEXT;
    ALTER TABLE runs ADD COLUMN stage TEXT;
    ALTER TABLE runs ADD COLUMN transcript TEXT;
    """,
    # Retros (Joe, 2026-10-25): why one was filed, and the runs behind it, for its PR's "Runs behind this".
    6: """
    ALTER TABLE tickets ADD COLUMN retro_reason TEXT;
    ALTER TABLE tickets ADD COLUMN retro_runs TEXT;
    """,
    # Head-to-head (Joe, 2026-10-25): re-runs of done tickets from their base commit, one row per engine.
    7: """
    CREATE TABLE bench (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticket TEXT NOT NULL,
        agent TEXT NOT NULL,
        base_sha TEXT,
        started_at REAL NOT NULL,
        ended_at REAL,
        result TEXT,
        minutes REAL,
        tokens_in INTEGER,
        tokens_out INTEGER,
        cost_usd REAL,
        detail TEXT,
        check_output TEXT,
        run_dir TEXT,
        worktree TEXT
    );
    """,
    # Clearing things away (Joe, 2026-10-26): an archived repo and its tickets are off the board, out of stats and
    # never picked by the loop, with nothing deleted; a cleared ticket is off the board but still in stats.
    8: """
    ALTER TABLE repos ADD COLUMN archived_at REAL;
    ALTER TABLE tickets ADD COLUMN cleared_at REAL;
    """,
    # Several tickets at once (Joe, 2026-10-26): each runner's limits (slots is its max sessions) and its last
    # reading, and why a ready ticket is held back: its touches overlap a running one, or its Mac is busy.
    9: """
    ALTER TABLE runners ADD COLUMN per_session_mb INTEGER;
    ALTER TABLE runners ADD COLUMN max_load REAL;
    ALTER TABLE runners ADD COLUMN min_disk_gb REAL;
    ALTER TABLE runners ADD COLUMN reading TEXT;
    ALTER TABLE runners ADD COLUMN hold TEXT;
    ALTER TABLE tickets ADD COLUMN hold TEXT;
    """,
}

# Ticket states and the board column and stage each shows as.
STATES = {
    'queued': ('up_next', None),
    'building': ('running', 'build'),
    'checking': ('running', 'check'),
    'reviewing': ('running', 'review'),
    'merging': ('running', 'merge'),
    'needs_you': ('needs_you', None),
    'taken': ('needs_you', None),       # taken back by the person: waits in Needs you until given back
    'done': ('done', None),
    'dropped': ('done', None),
}


class RunwayError(Exception):
    pass


def home():
    return Path(os.environ.get('RUNWAY_HOME') or Path.home() / '.runway')


def db_path():
    return home() / 'runway.db'


def connect(path=None):
    path = Path(path or db_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path), timeout=10, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA journal_mode=WAL')
    con.execute('PRAGMA foreign_keys=ON')
    migrate(con)
    return con


def migrate(con):
    has_meta = con.execute("SELECT 1 FROM sqlite_master WHERE name='meta'").fetchone()
    version = 0
    if has_meta:
        row = con.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        version = int(row['value']) if row else 0
    if 0 < version < SCHEMA_VERSION:
        back_up(con, version)
    for v in range(version + 1, SCHEMA_VERSION + 1):
        con.executescript('BEGIN;\n' + MIGRATIONS[v]
                          + f"\nINSERT OR REPLACE INTO meta(key, value) VALUES ('schema_version', '{v}');\nCOMMIT;")
    if version == 0:
        seed(con)
    else:
        if version < 4 <= SCHEMA_VERSION:
            backfill_v4(con)
        if version < 5 <= SCHEMA_VERSION:
            backfill_v5(con)


KEEP_BACKUPS = 5


def back_up(con, version):
    """Before a migration changes it: a copy of the database in ~/.runway/backups/runway-v<old schema>-<time>.db,
    keeping the newest five. Uses SQLite's own backup, so the copy is consistent while the app and loop are open."""
    path = next((r['file'] for r in con.execute('PRAGMA database_list') if r['name'] == 'main'), '')
    if not path:
        return None                                   # an in-memory database: nothing to keep
    folder = Path(path).parent / 'backups'
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / f'runway-v{version}-{time.strftime("%Y%m%d-%H%M%S")}.db'
    n = 1
    while dest.exists():
        dest = folder / f'runway-v{version}-{time.strftime("%Y%m%d-%H%M%S")}-{n}.db'
        n += 1
    out = sqlite3.connect(str(dest))
    try:
        con.backup(out)
    finally:
        out.close()
    for old in sorted(folder.glob('runway-v*.db'), key=lambda p: p.stat().st_mtime)[:-KEEP_BACKUPS]:
        old.unlink()
    return dest


def backfill_v5(con):
    """Runs from before version 5: the last stage they reached, from their outcome, and their transcript linked into
    their folder, so take back's prompt and runway show can point at them."""
    from . import worker
    stage = {'done': 'reviews', 'pass': 'review done', 'fail': 'review done', 'failed': 'failed',
             'limited': 'usage limit', 'needs_you': 'asked a question'}
    for r in con.execute('SELECT * FROM runs WHERE run_dir IS NULL').fetchall():
        folder = home() / 'runs' / str(r['id'])
        transcript = None
        if folder.exists():
            transcript = worker.link_transcript(r['agent'], r['session_id'], folder)
        con.execute('UPDATE runs SET stage=COALESCE(stage, ?), transcript=COALESCE(transcript, ?) WHERE id=?',
                    (stage.get(r['outcome'] or '', r['outcome'] or r['kind']), transcript, r['id']))


def backfill_v4(con):
    """Existing databases: merges and stops from the event log, tokens and cost from each run's own log."""
    from . import worker
    for e in con.execute("SELECT ticket, at, text FROM events WHERE kind='merged' AND ticket IS NOT NULL ORDER BY id"):
        con.execute('UPDATE tickets SET merged_at=?, merged_by=? WHERE id=? AND merged_at IS NULL',
                    (e['at'], 'you' if 'merged by you' in e['text'] else 'gate', e['ticket']))
    for e in con.execute("SELECT e.ticket, e.at, e.text, t.repo FROM events e JOIN tickets t ON t.id = e.ticket "
                         "WHERE e.kind='needs_you' ORDER BY e.id"):
        con.execute('INSERT INTO stops(ticket, repo, at, reason, detail) VALUES (?, ?, ?, ?, ?)',
                    (e['ticket'], e['repo'], e['at'], reason_from_text(e['text']), e['text']))
    for r in con.execute('SELECT id, agent FROM runs WHERE cost_usd IS NULL AND tokens_in IS NULL'):
        log = home() / 'runs' / str(r['id']) / 'log'
        if log.exists():
            tin, tout, cost = worker.usage(r['agent'], log.read_text(errors='replace'))
            con.execute('UPDATE runs SET tokens_in=?, tokens_out=?, cost_usd=? WHERE id=?', (tin, tout, cost, r['id']))


def reason_from_text(text):
    """An old needs-you event's reason, from its wording."""
    t = text.lower()
    if 'not low risk' in t:
        return 'not_low_risk'
    if 'sensitive paths' in t:
        return 'sensitive_path'
    if ' asked: ' in t:
        return 'worker_question'
    if 'failed twice' in t:
        return 'failed_twice'
    return 'other'


def seed(con):
    """A fresh database knows this Mac and the two engines it can use; setup records which are signed in."""
    con.execute("INSERT OR IGNORE INTO runners(name, kind, slots) VALUES ('This Mac', 'this_mac', 2)")
    for kind in ('claude', 'codex'):
        con.execute('INSERT OR IGNORE INTO agents(kind) VALUES (?)', (kind,))
    con.execute("INSERT OR IGNORE INTO meta(key, value) VALUES ('next_ticket', '1')")


def now():
    return time.time()


def meta(con, key, default=None):
    row = con.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()
    return row['value'] if row else default


def set_meta(con, key, value):
    if value is None:
        con.execute('DELETE FROM meta WHERE key=?', (key,))
    else:
        con.execute('INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)', (key, str(value)))


def event(con, kind, text, repo=None, ticket=None):
    con.execute('INSERT INTO events(at, kind, repo, ticket, text) VALUES (?, ?, ?, ?, ?)',
                (now(), kind, repo, ticket, text))


def run_dir(con, run):
    """A run's folder: ~/.runway/runs/<ticket>/<n>/ (runs from before version 5: ~/.runway/runs/<id>/)."""
    if isinstance(run, int):
        run = con.execute('SELECT * FROM runs WHERE id=?', (run,)).fetchone()
    path = Path(run['run_dir']) if run['run_dir'] else home() / 'runs' / str(run['id'])
    path.mkdir(parents=True, exist_ok=True)
    return path


def next_ticket_id(con):
    n = int(meta(con, 'next_ticket', '1'))
    set_meta(con, 'next_ticket', n + 1)
    return f'T-{n}'


def ticket(con, tid):
    row = con.execute('SELECT * FROM tickets WHERE id=?', (tid,)).fetchone()
    if not row:
        raise RunwayError(f'no ticket {tid}')
    return row


def repo(con, name):
    row = con.execute('SELECT * FROM repos WHERE name=?', (name,)).fetchone()
    if not row:
        raise RunwayError(f'no repo {name} (add it with: runway repo add <path>)')
    return row


def update_ticket(con, tid, **fields):
    fields['updated_at'] = now()
    for key in ('question',):
        if key in fields and fields[key] is not None and not isinstance(fields[key], str):
            fields[key] = json.dumps(fields[key])
    cols = ', '.join(f'{k}=?' for k in fields)
    con.execute(f'UPDATE tickets SET {cols} WHERE id=?', (*fields.values(), tid))


def blockers(con, tid):
    return [r['blocked_by'] for r in con.execute('SELECT blocked_by FROM blockers WHERE ticket=? ORDER BY blocked_by',
                                                 (tid,))]
