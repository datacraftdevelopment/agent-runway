# pm-runway

One plugin for the whole way of working, from a foggy idea to merged code on your own machines.

- **You shape, hands-on.** `whats-next` opens a session, `stepping-away` closes it. `wayfinder` charts foggy work into chunks; `brainstorming` talks a chunk through; `to-spec` writes it down with Acceptance lines; `to-tickets` cuts it into tracer-bullet tickets and files them on your go.
- **The machines build, unattended.** `runway start`, then `runway loop` in an Orca tab. Each ticket is built by a fresh session on whichever Mac is free, reviewed by the other model, and landed on the chunk's branch. The whole chunk is reviewed once, and the gate merges it to main only when it is low risk. Everything else waits for you as one card per chunk, never a pile of ticket PRs.
- **You ask, any time.** `runway-ask` answers "what's happening with inbox-03?", "what's waiting on me?", "spot-check the last three tickets", reading the files and Orca fresh each time.

Read [`RUNWAY.md`](./RUNWAY.md) for the ticket format, the loop and the gate, and [`WORKFLOW.md`](./WORKFLOW.md) for the hand-run session flow it shares with pm-sp.

```
/plugin marketplace add datacraftdevelopment/dc-dev-plugins
/plugin install pm-runway@dc-dev-plugins
```

**Install it instead of pm-sp or pm, never alongside them**, and without upstream Superpowers or Matt Pocock's skills: pm-runway carries what it uses ([`VENDOR.md`](./VENDOR.md)), and the shared skill names and credential guard would clash.

## What's in it

**Everything in pm-sp:** the trimmed Superpowers workflow (brainstorming with the visual companion, writing-plans, subagent-driven-development, finishing a branch, TDD, debugging, verification), Matt Pocock's wayfinder, grilling, domain-modeling, codebase-design, prototype, research and pr, `design-handoff` (screens shaped in Claude Design on a real data sample before anything is built), and pm-sp's session layer (whats-next, stepping-away, checkpoint, nested-sessions, second-opinion, ship-acceptance), the credential guard hook, gate-hooks, review-policy and ui-test.

**Matt Pocock's ticket flow, as our own versions:** `to-spec`, `to-tickets`, `implement-spec`, plus his `tdd` and `code-review` verbatim.

**Runway:** `work-ticket` and `review-ticket` (the contracts for the sessions Orca starts), `runway-ask` (the coordinator you talk to), and the `runway` CLI (`bin/runway`, standard-library Python): the readiness check, the chunk journal, the loop with its status screen and board page, and the gate.

## What it needs

On every machine that builds: the **Claude Code CLI** and the **Codex CLI**, both signed in with your own subscriptions; `git`, `gh` signed in, `python3` 3.9 or newer; and **Orca** (onorca.dev). The controller pairs the other Macs in Orca over Tailscale. The [setup guide](../SETUP.html) walks a person through it, and [`SETUP-AGENT.md`](../SETUP-AGENT.md) is the same setup for an agent to run.

Ringer is optional: with it, `second-opinion` and `ui-test` route Codex through it; without it, `second-opinion` calls Codex directly.

Put the CLI on your PATH once per machine:

```bash
ln -sf "$(find ~/.claude/plugins -path '*pm-runway*/bin/runway' -type f | sort | tail -1)" ~/.local/bin/runway
```

Tests: `python3 -m unittest discover -s tests` from the runway-agent repo root.
