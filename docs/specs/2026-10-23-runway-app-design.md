# Runway: our own simple app, tickets filed from normal sessions

Status: design, 2026-10-23. Talked through with Joe in the project's "Simple Runway app over SSH" thread. Nothing built.
Supersedes the Orca-based design on branch `claude/project-thread-4tbxvb` (PR #3): Joe tried Orca and found it too
technical to hand to a newcomer ("a super terminal"). No Orca, no Herdr.

## The idea in one paragraph

People keep working in Claude Code or Codex exactly as they do now. When part of the work can run on its own, the
agent in that session proposes tickets, the person says go, and the tickets are filed. Runway picks them up, runs each
one headless on a free Mac (this one, or another reached over SSH), has the other agent review it, and the result comes
back as a pull request: merged on its own when it is low risk, otherwise waiting for the person. A small Mac app shows
what's up next, what's running, what needs you and what's done, in the look of Runway v1's app.

## Decisions

- **The front door is a skill, not the app.** `file-tickets` runs inside the person's normal Claude Code or Codex
  session. It proposes a short batch (title, what done looks like, risk, what it touches, what it waits on), and files
  only on the person's go, typed in that session. That go is the approval; Runway never files on its own.
- **Tickets travel by git.** Filing commits ticket files to one dedicated branch in the repo, `runway/tickets`, which is
  never merged and needs no branch protection. It works the same from any Mac or a cloud session, with nothing to
  connect to. Each ticket names its base branch; the skill pushes that branch first.
- **A ticket is a Markdown file** (`runway/tickets/<id>.md` on that branch): frontmatter for `id`, `base`, `risk`
  (`low` only with a one-line reason; default `not-low`), `touches`, `blocked_by`, `agent` (`any`, `claude`, `codex`),
  then the task and its Acceptance lines. A ticket points at a spec when there is one and never restates it.
- **One Mac is enough.** By default Runway runs tickets on the same Mac the app is on. Other Macs are an option added
  later in the app, reached over plain SSH (Tailscale SSH recommended). Nothing is installed on another Mac except
  Claude Code, Codex, git and tmux, which it needs anyway.
- **Workers run headless.** `claude -p` or `codex exec` with JSON output, in a fresh git worktree, inside tmux so a
  dropped SSH connection or a closed app doesn't kill the run. Each run writes one outcome file
  (`done`, `blocked`, `needs-you` with one question, `failed`) that the loop reads back.
- **Review by the other agent,** pinned to the exact commit, against the ticket's Acceptance lines. It can raise risk,
  never lower it. With only one agent signed in, the best a review can say is needs-you, so nothing auto-merges on a
  model reviewing itself.
- **Merge gate as code:** auto-merge only when risk is `low`, the review passed on the head commit, checks are green,
  and no changed path is sensitive (auth, payments, migrations, CI, the repo's `runway.json`). Everything else is a
  needs-you card with the PR link.
- **Usage-limit failover** (Joe, 2026-10-23, kept from PR #3): when one agent's limit error stops a run, the ticket goes
  back to the queue without spending its fix pass and `any` tickets go to the other agent until the reset.
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
| `runway` CLI | Python, stdlib only. `file`, `loop`, `status --json`, `pause`/`resume`, `go`/`no`, `doctor`. State in `~/.runway/` (journal JSON per repo, `machines.json`, `limits.json`). | `journal.py`, `loop.py`, `gate.py`, `tickets.py` from PR #3, with Orca calls swapped for ssh/tmux |
| `file-tickets` skill | For Claude Code and Codex. Proposes the batch, files on go, pushes `runway/tickets`. | PR #2/#3 skill text, trimmed |
| `work-ticket` skill | What a headless worker follows: build in the worktree, open a draft PR, write the outcome file. | PR #2 |
| `review-ticket` skill | The other agent's review and verdict. | PR #2 |
| `runway` skill | From any session: what's running, what needs me, pause, resume, go/no. | v1's `runway` skill idea |
| The app | Menu bar + side panel + one window. | Runway v1's SwiftUI app (archived `runway` repo) |

## The app (Runway v1's look, new insides)

- **Menu bar:** one dot per repo (running, idle, needs you, paused, off).
- **Side panel**, keep-on-top: one card per repo with Start/Stop, what's running now and elapsed time, the last few
  activity lines.
- **Window:** a sidebar of repos, then two tabs. **Board:** Needs you, Up next, Running, Done, with no drag and drop
  (moving a card is never a go). **Activity:** the log, as in v1's window. Clicking a card opens an inspector: the
  ticket, its PR, the review, Go/No with a note for needs-you cards, Open session.
- **First run:** "This Mac" checks `claude`, `codex`, `git`, `gh`, `tmux` and the two sign-ins, green or red with a fix
  for each red; then "Add a repo" (pick a folder, write `runway.json`, install the skills). "Add a Mac" is a separate
  button later: SSH reachable, tools there, sign-ins work inside a non-interactive SSH session.

## Acceptance

- [ ] A1: On a Mac with Claude Code and Codex signed in and no other Mac, the app's first run goes green and adds a
  practice repo. Verify: run it on a second Mac from a fresh clone.
- [ ] A2: In an ordinary Claude Code session in the practice repo, asking for two small tickets and typing go puts them
  in Up next within one loop tick; both run, each is reviewed by Codex, the low-risk one merges on its own and the
  `not-low` one lands in Needs you with its PR. Verify: the board during the run, `git log main` after.
- [ ] A3: The same filing from a Codex session works, and the ticket is built by Claude Code. Verify: one ticket,
  `agent: claude`.
- [ ] A4: With a second Mac added over SSH, a ticket runs there; closing the app mid-run doesn't kill it, and reopening the
  app shows its result. Verify: quit the app during the run.
- [ ] A5: When one agent's usage limit stops a run, the ticket requeues without spending its fix pass and the board
  shows that agent resting until its reset. Verify: the next real limit, or a stub worker that prints the limit error.

## Open, to settle while building

- **App stack.** SwiftUI (Joe liked v1's app; its code can be copied from the archive) or a web UI in a Tauri shell
  (the earlier choice, works beyond macOS). Asked of Joe. v1 built with
  `swift build`; whether Command Line Tools alone are enough for SwiftUI is untested.
- **Keychain over SSH.** Claude and Codex sign-ins may be locked in a non-interactive SSH session. Test on a second Mac
  before building the multi-Mac part; one Mac (A1 to A3) doesn't depend on it.
- **Codex headless flags** (`codex exec --json`, `codex resume`) to confirm against the installed version.
