# runway-agent plugin

The skills and the controller CLI for Runway Agent. Version 0.1.0 covers the loop only: file a ticket, dispatch it to a worker through Herdr, pull its receipts, review it on the other model, gate the merge. The setup wizard, the board skill and steered-session scanning come after the loop has run for real.

| Piece | What it is |
|---|---|
| `skills/file-tickets` | End of shaping: cut a plan into tickets with risk set, file them on the operator's go |
| `skills/work-ticket` | What a dispatched worker session follows: claim check, build, draft PR, typed receipts |
| `skills/review-ticket` | The review seat and the gate's rules |
| `bin/runway-agent` | The CLI. Controller commands use `~/.runway-agent/runway.db`; `claim-check` and `receipt` are the worker's and never open it |
| `templates/` | `runway.json`, `docs/agents/worker-env.md` and the review prompt |

Needs `python3` (3.9+), `git`, and `gh` signed in on the controller (the gate) and on each worker (pushes, draft PRs). Nothing else; no pip installs.

## Install

On every machine (controller and workers):

```
/plugin marketplace add datacraftdevelopment/runway-agent
/plugin install runway-agent@runway-agent
```

Then put the CLI on PATH, so the controller and SSH sessions find it:

```bash
ln -s ~/.claude/plugins/cache/runway-agent/runway-agent/<version>/bin/runway-agent ~/.local/bin/runway-agent
runway-agent init
```

(The cache path varies by Claude Code version; `find ~/.claude/plugins -path '*runway-agent/bin/runway-agent'` finds it.)

Each worker also needs its label, which receipts carry: `echo '{"label": "worker-1"}' > ~/.runway-agent/machine.json`.

## Controller setup

```bash
runway-agent project add DEMO --repo you/demo --path ~/code/demo      # the controller's clone, for the gate
runway-agent machine add worker-1 --ssh-host worker-1.tailnet.ts.net   # --herdr-label if Herdr knows it by another name
```

In the repo: copy `templates/runway.json` to the root (set `check_cmd`) and `templates/worker-env.md` to `docs/agents/worker-env.md`, and commit both on the default branch.

## Launching through Herdr

`dispatch --launch` sends the packet over SSH and runs the `herdr_launch` command from `~/.runway-agent/config.json`. The template is yours to write, because Herdr's flags must match your Herdr version; the CLI fills `{herdr_label}`, `{machine}`, `{dispatch_id}`, `{ticket}`, `{packet_path}` and `{prompt}`. The session must start with `RUNWAY_DISPATCH_ID={dispatch_id}` in its environment and `{prompt}` as its first message. Shape only, not checked against Herdr 0.9.5:

```json
{
  "herdr_launch": ["herdr", "--machine", "{herdr_label}", "agent", "start", "--env", "RUNWAY_DISPATCH_ID={dispatch_id}", "--", "claude", "{prompt}"],
  "herdr_list": ["herdr", "--machine", "{herdr_label}", "agent", "list", "--json"],
  "models": ["claude", "codex"]
}
```

Without `herdr_launch`, `dispatch` still claims and prints the packet; start the session by hand with the env var set.

## The loop by hand

```bash
runway-agent ticket add DEMO --title "…" --spec docs/specs/x.md --risk low --risk-reason "…"   # file-tickets does this
runway-agent dispatch DEMO-1 --machine worker-1 --launch      # the claim: one live attempt per ticket
runway-agent pull                                             # receipts from every worker's outbox, deduped
runway-agent reap                                             # sessions Herdr says ended with no receipt -> failed
runway-agent review run DEMO-1                                # the other model, on the head from build-done
runway-agent gate DEMO-1                                      # merge, or a needs-you card
runway-agent decisions                                        # open needs-you cards
runway-agent answer 3 merge --by <you>                        # only the operator answers
runway-agent ticket list
```

## Not checked yet

- The Herdr templates above, and whether `claude -p --permission-mode plan` lets the review seat run `git diff` (if not, switch the seat to an allowlist of read-only tools).
- `claude -p` and `codex exec` sign-ins inside a non-interactive SSH session on a worker (the keychain risk). That's the first spike.

Tests: `python3 -m unittest discover -s tests` from the repo root.
