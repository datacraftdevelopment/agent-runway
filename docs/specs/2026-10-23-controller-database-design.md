# Controller database and Herdr first

Status: decided 2026-10-23 in conversation with Joe. Amends ruling 3 of `docs/review/2026-10-23-panel.md` (where ticket definitions live).

## Decision

1. **Herdr is the worker layer, and we start with it.** BB was the other candidate; it keeps sessions alive across machines and is good to watch, but it can't start work or report agent state to a script. Herdr does both over SSH with JSON output. BB could come later as a viewer if it earns a place.
2. **The app gets a database: one SQLite file on the controller.** No server, nothing hosted, nothing for a new user to set up. It ships with macOS and every language we'd use.
3. **The database is also the ticket tracker.** This was always the plan (the old hosted runway-db); it just moves onto the controller. It replaces the panel's "ticket files committed in each repo".

## What lives where

| Fact | Where | Who writes it |
|---|---|---|
| Projects, tickets, what blocks what, comments | Controller SQLite | The filing skill (through the controller's CLI), Joe from the app |
| Claims, attempts, receipts, review verdicts, decisions | Controller SQLite | The controller only |
| Machines and their settings | Controller SQLite | Setup |
| Specs, plans, design docs | Git, in each repo | Shaping sessions |
| Live agent state (idle, working, blocked, done) | Herdr on each worker | Herdr; read, never stored as truth |

The board reads the database and Herdr; it stores nothing of its own.

## Why SQLite and not log files

- **Claims must be atomic.** Two dispatches must never both win a ticket. A SQLite transaction guarantees that; appending to a file does not.
- **The board needs queries** (by machine, by status, needs-you first). Files would need an index anyway.
- **Every change is also kept as an event row** (append-only), so the history the panel asked for stays: ids on every event, replay is safe, receipts pulled twice are deduplicated by id.

## Tables

As built in `plugin/runway_agent/store.py` (first cut plus what the loop needed, marked *added*):

- `projects` (id, key, name, repo, *path*: the controller's clone the gate reads `runway.json` from, default_branch)
- `tickets` (id, project_id, number, title, body, risk, *risk_reason*, status, strategy, spec_path, *plan_path*, *acceptance*, *touches*, *model*, created_at)
- `ticket_blocks` (ticket_id, blocked_by_id)
- `comments` (id, ticket_id, author, body, created_at)
- `machines` (id, label, herdr_label, *ssh_host*, kind: local/ssh/cloud, enabled)
- `attempts` (id, ticket_id, dispatch_id, machine_id, herdr_session, branch, started_at, ended_at, outcome). A partial unique index allows one live attempt (ended_at null) per ticket: that index is the claim.
- `events` (id, at, kind, ticket_id, attempt_id, payload JSON), append-only. Receipts keep their own id, so a replay is ignored.
- `sessions` (machine_id, agent, session_id, folder, started_at, last_seen_at, source)
- `decisions` (id, ticket_id, *kind*: build/review/gate, question, options, *recommended*, answer, answered_by, answered_at, *revision*)

Risk is written at filing and can only go up (reviewer raises are events). `tickets.status` is a cache that only the event writer updates; nothing edits it by hand.

## How tickets reach a worker

The controller passes the ticket body, its spec path and the dispatch id when it starts the session through Herdr (`herdr --machine <label> agent start …`). The worker never reads the database; it reports through its local outbox, which the controller pulls over SSH, as the panel ruled. Cloud sessions get the same packet in their start prompt and report through result files on their branch.

## Steered sessions (found, not reported)

Joe's own sessions (Claude Code or Codex, in the terminal or the desktop app, on any machine) show on the board without anything installed. Desktop doesn't run plugin hooks, so a session hook can't be the source.

- Claude Code writes a log file per session under `~/.claude/projects/<folder>/<session-id>.jsonl`. On each refresh the controller lists recent files on every machine over SSH (`find ~/.claude/projects -name '*.jsonl' -mmin -N`, plus file times), and reads only the first lines for the folder and start time. Codex does the same under `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` (first line holds the folder), scanned the same way.
- A session counts as active if its file changed in the last few minutes, idle otherwise. Sessions the controller started itself (it knows their ids from `attempts`) are left out, so tickets aren't shown twice.
- Stored in a `sessions` table (machine_id, session_id, folder, started_at, last_seen_at, source: scan, agent: claude/codex). The board shows them as steered; the controller never drives them.
- Where a hook does run (terminal Claude Code with the plugin), it may add detail (a title, the branch) through the outbox. Nothing depends on it.
- To check on the first try: that the Claude desktop app's Code tab and the Codex desktop app write these same log files. If it doesn't, desktop sessions won't show until we find where it keeps them.

## Consequences

- The gate's trust problem gets simpler: ticket definitions are no longer in the repo the builder edits, so a builder can't rewrite its own ticket or risk.
- Tickets don't travel with the code. If a repo moves to another person's controller, its open tickets need an export. Acceptable for v1.
- Back up one file (`~/.runway-agent/runway.db`). Time Machine covers it.
- The filing skill writes through the controller's CLI, so a shaping session on another Mac files over SSH (`ssh controller runway-agent ticket add …`). Shaping on the controller itself is the common case.

## Acceptance

- [ ] A1: `runway-agent ticket add` on the controller creates a ticket row and a `filed` event, and `runway-agent ticket list` shows it.
- [ ] A2: Two dispatches of the same ticket started at once: exactly one gets a claim, the other is refused.
- [ ] A3: One low-risk ticket runs on a worker through Herdr, its receipt is pulled into the database, and the board shows it done.
- [ ] A4: Pulling the same receipts twice leaves one event per receipt.
- [ ] A5: A session started by hand in Claude Code desktop and one in Codex desktop on a worker each appear on the board as steered within one refresh, with its folder.
