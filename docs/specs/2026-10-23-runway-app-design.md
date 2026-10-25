# Runway: our own simple app, tickets filed from normal sessions

Status: design, 2026-10-23. UI mock: https://claude.ai/artifact/MzYxCva9uyogGxmEKFFNJ3. Talked through with Joe in the project's "Simple Runway app over SSH" thread. Nothing built.
Supersedes the Orca-based design on branch `claude/project-thread-4tbxvb` (PR #3): Joe tried Orca and found it too
technical to hand to a newcomer ("a super terminal"). No Orca, no Herdr.

## The idea in one paragraph

People keep working in Claude Code or Codex exactly as they do now. When part of the work can run on its own, the
agent in that session proposes tickets, the person says go, and the tickets are filed. Runway picks them up, runs each
one headless on a free runner (this Mac, another Mac over SSH, or the cloud), reviews it in two fresh sessions, and the result comes
back as a pull request: merged on its own when it is low risk, otherwise waiting for the person. A small Mac app shows
what's up next, what's running, what needs you and what's done, in the look of Runway v1's app.

## Decisions

- **The front door is a skill, not the app.** `file-tickets` runs inside the person's normal Claude Code or Codex
  session. It proposes a short batch (title, what done looks like, risk, what it touches, what it waits on), and files
  only on the person's go, typed in that session. That go is the approval; Runway never files on its own.
- **One local database, nothing hosted** (Joe, 2026-10-23). A single SQLite file on the Mac that runs Runway
  (`~/.runway/runway.db`) holds tickets, blockers, runs, reviews, go/no answers and history. It is the only source of
  truth; the app, the loop, the `runway` skill and the CLI all read and write it. Specs and PRs stay in git; a
  ticket points at them and never restates them.
- **Filing goes straight into the database.** On the person's go, the skill runs `runway file`: directly on the
  Runway Mac, over SSH from another Mac. A cloud session can't reach the Mac, so it pushes ticket files to a dedicated
  `runway/tickets` branch (never merged, needs no protection) and Runway imports them on its next tick.
- **A ticket's fields:** `id`, `repo`, `base` branch, `risk` (`low` only with a one-line reason; default `not-low`),
  `touches`, `blocked_by`, `agent` (`any`, `claude`, `codex`), the task, and its Acceptance lines. The cloud file
  form is the same fields as Markdown frontmatter plus body.
- **Several Macs, cloud, Claude Code and Codex from the start** (Joe, 2026-10-23). A "runner" is a place a ticket
  can run: this Mac, another Mac reached over plain SSH (Tailscale SSH recommended), or the cloud (Claude Code on the
  web and Codex cloud, started from the Runway Mac with the person's own accounts). Each runner has slots; each ticket
  goes to a free one that has the agent it needs. Nothing is installed on another Mac except Claude Code, Codex, git,
  tmux and the Runway skills.
- **Each repo has a main computer, and work can be pinned** (Joe, 2026-10-23). The main computer is where the repo's
  local folder lives; the sidebar shows it. A repo's "Runs on" is any runner (default) or its main computer only, and
  a ticket can override it with one named runner (for example, because a folder it needs only exists there). A pinned
  ticket waits for a free slot on that runner even when others are free.
- **Claude Code, Codex and Any have their own colours** everywhere a ticket or agent appears (Joe, 2026-10-23).
- **Setup is shared between the app and an agent** (Joe, 2026-10-23). The app lays the groundwork (installs the
  `runway` command, creates the database, adds the Runway skills to Claude Code and Codex), then hands over to a
  `setup` skill the person runs in their agent: it checks sign-ins, adds the computer as a runner, asks which repos to
  watch, and writes what it found into the database, which the app shows live. On another Mac, the same skill with
  `join` adds that Mac; for cloud, it connects the person's Claude and Codex cloud accounts.
- **Workers run headless.** `claude -p` or `codex exec` with JSON output, in a fresh git worktree, inside tmux so a
  dropped SSH connection or a closed app doesn't kill the run. Each run writes one outcome file
  (`done`, `blocked`, `needs-you` with one question, `failed`) that the loop reads back.
- **One engine is enough** (ruling, Joe, 2026-10-25). Runway works fully with only Claude Code or only Codex,
  including a ~$20 plan; never assume both. Setup is green with one engine signed in, and the other shows as optional.
  A ticket's agent `any` means any signed-in engine, and a ticket naming an engine this Mac doesn't have is refused at
  filing. The app shows only the engines that exist. This replaces the earlier rule that a one-model review caps at
  needs-you.
- **Review is two fresh sessions** (ruling, Joe, 2026-10-25), each with its own prompt and none of the builder's
  context, pinned to the exact head commit:
  - the **code review**: correctness, bugs, risk, sensitive paths, tests worth having;
  - the **function review**: checks out the head commit, runs the check command and walks each Acceptance line,
    pass or fail per line with evidence.
  Both must pass on the same head commit for the gate; either can fail it, and either can raise the risk (never lower
  it). With one engine both run on it, and their passes count. With two, the code review prefers the other engine from
  the builder and the function review runs on either; cross-model review is preferred, not required. Both verdicts are
  stored per run and shown in the inspector (Code review, Function review).
- **Merge gate as code:** auto-merge only when risk is `low`, both reviews passed on the head commit, checks are
  green, and no changed path is sensitive (auth, payments, migrations, CI, the repo's `runway.json`). Everything else
  is a needs-you card with the PR link.
- **Usage limits** (Joe, 2026-10-23, kept from PR #3; one-engine case, 2026-10-25): when an engine's limit error stops
  a run, the ticket goes back to the queue without spending its fix pass, and the board shows that engine resting until
  the reset. With two engines, `any` tickets go to the other one until then; with one, the ticket simply waits (it
  doesn't fail, and no failover is attempted).
- **The loop is a plain script, not an agent,** and it runs only while the app is open, as the app's child process.
  No LaunchAgent, no daemon, nothing hidden. Closing the app pauses dispatch; runs already started finish in tmux and
  are picked up when the app opens again.
- **The app holds no logic.** It reads `runway status --json` and runs `runway` commands. Every rule lives once, in
  the Python CLI, so the app, the `runway` skill and a terminal all see the same thing.
- **Watching a run:** the card's "Open session" button opens Terminal on `claude --resume <id>` or
  `codex resume <id>` on the Mac that ran it. Handing off to Claude Desktop's or the Codex app's own SSH sessions is a
  later nice-to-have (both support SSH remotes; deep links into a specific session are unverified).
- **Public from day one.** No personal paths, machine names, client names, or dependency on private tools (Ringer is
  not used).

## The pieces

| Piece | What it is | Reused from |
| --- | --- | --- |
| `runway` CLI | Python, stdlib only. `file`, `loop`, `status --json`, `pause`/`resume`, `go`/`no`, `doctor`. State in `~/.runway/runway.db` (SQLite, stdlib `sqlite3`); `import` pulls cloud-filed tickets from `runway/tickets`. | `loop.py`, `gate.py`, `tickets.py` from PR #3 with Orca swapped for ssh/tmux; `store.py` (SQLite) from PR #2 |
| `file-tickets` skill | For Claude Code and Codex. Proposes the batch, files on go with `runway file` (or the `runway/tickets` branch from a cloud session). | PR #2/#3 skill text, trimmed |
| `work-ticket` skill | What a headless worker follows: build in the worktree, open a draft PR, write the outcome file. | PR #2 |
| `review-ticket` skill | Superseded: the code and function review prompts live in the CLI (`runway/worker.py`). | PR #2 |
| `runway` skill | From any session: what's running, what needs me, pause, resume, go/no. | v1's `runway` skill idea |
| `setup` skill | Run by the person's agent: sign-ins, add this computer (or `join` another Mac, or connect cloud), pick repos. | PR #2's setup outline |
| The app | SwiftUI: menu bar + side panel + one window. | Runway v1's SwiftUI app (archived `runway` repo) |

## The app (Runway v1's look, new insides)

- **Menu bar:** one dot per repo (running, idle, needs you, paused, off).
- **Side panel**, keep-on-top: one card per repo with Start/Stop, what's running now and elapsed time, the last few
  activity lines.
- **Window:** a sidebar of repos, then two tabs. **Board:** Needs you, Up next, Running, Done, with no drag and drop
  (moving a card is never a go). **Activity:** the log, as in v1's window. Clicking a card opens an inspector: the
  ticket, its PR, the review, Go/No with a note for needs-you cards, Open session.
- **First run:** three steps on one screen. Runway does its part (command, database, skills); a button opens Claude
  Code or Codex on `/runway:setup`; a copyable `join` command for each other Mac and a cloud connect step. Below, a
  live table of what setup has found per runner (reachable, Claude Code, Codex, GitHub).
- **Where tickets run:** the sidebar lists runners with their load and each agent's state (available, or resting
  until a limit resets).

## Acceptance

- [ ] A1: On a Mac with Claude Code and Codex signed in, the app's first run plus `/runway:setup` in Claude Code adds
  this Mac and a practice repo; `join` on a second Mac adds it; the cloud step adds cloud. The live table goes green
  for all three. Verify: a fresh install on two Macs.
- [ ] A2: In an ordinary Claude Code session in the practice repo, asking for two small tickets and typing go puts them
  in Up next within one loop tick; both run, each is reviewed by the other agent, the low-risk one merges on its own
  and the `not-low` one lands in Needs you with its PR. Verify: the board during the run, `git log main` after.
- [ ] A3: Tickets filed from a Codex session, from the second Mac, and from a cloud session (via the tickets branch)
  all reach Up next; across a run, tickets land on this Mac, the second Mac and the cloud. Verify: the board's runner
  column during the run.
- [ ] A4: Quitting the app mid-run doesn't kill a ticket running on another Mac or in the cloud, and reopening the app
  shows its result. Verify: quit the app during the run.
- [ ] A5: When one agent's usage limit stops a run, the ticket requeues without spending its fix pass and the board
  shows that agent resting until its reset. Verify: the next real limit, or a stub worker that prints the limit error.

## Open, to settle while building

- **App stack: decided SwiftUI** (Joe, 2026-10-23), reusing v1's views from the archive copy (the `runway` repo
  stays archived). Mac only. Whether Command Line Tools alone are enough for `swift build` of a SwiftUI app is
  untested; check it first.
- **Keychain over SSH.** Claude and Codex sign-ins may be locked in a non-interactive SSH session. First thing to test
  on a second Mac.
- **Starting cloud runs from the Mac.** The commands that start a Claude Code web session and a Codex cloud task from
  a terminal, and how their result is read back (the PR is the reliable signal), are unverified.
- **Codex headless flags** (`codex exec --json`, `codex resume`) to confirm against the installed version.
