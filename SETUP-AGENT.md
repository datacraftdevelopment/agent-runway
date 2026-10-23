# pm-runway setup: the agent's runbook

You are an agent (Claude Code or Codex) setting up pm-runway on a person's Macs. The person's guide is `SETUP.html`; this is the same setup with every command and check. Work through the steps in order, on the machine each step names. Run `setup/doctor.sh` after each machine; a step is done when its checks pass, not when its commands ran.

## The shape

- **The controller** is one Mac that is usually awake. It runs the Orca app, the loop (`runway loop`) in an Orca tab, and the gate. It is also a worker.
- **Workers** are the other Macs. Each runs the Orca app, paired to the controller over Tailscale, and builds or reviews whatever the loop starts there.
- **Every machine** that builds needs the Claude Code CLI and the Codex CLI, signed in with the person's own subscriptions. Desktop apps of either are not needed.

Nothing runs as a hidden service. The loop is a terminal tab the person can see and stop.

## Rules for you

- **Ask before anything the person must do with their own hands or accounts:** signing in (Claude, Codex, GitHub, Tailscale), approving macOS permission prompts, pairing links, uninstalling another plugin. Say exactly what to click or type, then wait and re-check.
- **Never print, copy or store a credential or an Orca pairing link** anywhere but where the step puts it. A pairing link grants control of that Mac's Orca: it goes from one Orca window to the other and nowhere else.
- **Never write machine names, paths or account names into the runway-agent repo** or any public repo. They go in `~/.pm-runway/machines.json` on the controller.
- **Check facts against the installed versions** (`--help`, `orca skills get orchestration`) where this runbook and the tool disagree, and tell the person what differed.

## Step 1. Base tools (every machine)

```bash
xcode-select -p >/dev/null 2>&1 || xcode-select --install       # git and python3 (3.9+)
command -v brew || /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install gh
gh auth login            # the person signs in; choose HTTPS and "Login with a web browser"
gh auth setup-git
```

Check: `git --version`, `python3 --version` (3.9 or newer), `gh auth status`.

## Step 2. Claude Code CLI and Codex CLI (every machine)

```bash
curl -fsSL https://claude.ai/install.sh | bash      # Claude Code, native install
brew install codex                                   # or: npm install -g @openai/codex
```

Then the person signs in to each, with their own subscription, in a normal terminal:

- `claude`, then `/login`, choosing their Claude subscription.
- `codex login`, choosing "Sign in with ChatGPT".

Run each once in a scratch folder and answer the first-run prompts (trust the folder, theme), so a worker session never stops on them later. Check: `claude --version`, `codex --version`, `codex login status`. Install commands change; if one fails, take the current one from each tool's docs and note it for the person.

## Step 3. Tailscale (every machine)

```bash
brew install --cask tailscale
```

The person opens Tailscale and signs in with the **same account on every Mac**. Check: `tailscale status` lists every Mac (or the menu-bar app shows them). Note each Mac's Tailscale name; you need them in step 6.

## Step 4. Orca (every machine)

```bash
brew install --cask stablyai/orca/orca
open -a Orca
```

On first launch Orca asks for home-folder access and offers to import `~/.claude` and `~/.codex`: the person accepts both. Then make sure the `orca` command works in a normal terminal (`orca status --json`); if not, the person turns it on in Orca under **Settings → General → Orca CLI**. Install Orca's own agent skills:

```bash
orca skills install --skill orca-cli --skill orchestration
```

Check: `orca status --json` answers.

## Step 5. The pm-runway plugin (every machine)

pm-runway replaces pm-sp and pm. If either is installed, the person uninstalls it first (`claude plugin uninstall pm-sp@dc-dev-plugins`); you ask, they run it. Upstream Superpowers and Matt Pocock's skills go too, if present.

```bash
claude plugin marketplace add datacraftdevelopment/dc-dev-plugins
claude plugin install pm-runway@dc-dev-plugins
mkdir -p ~/.local/bin
ln -sf "$(find ~/.claude/plugins -path '*pm-runway*/bin/runway' -type f | sort | tail -1)" ~/.local/bin/runway
```

Make sure `~/.local/bin` is on PATH in `~/.zshrc` (`export PATH="$HOME/.local/bin:$PATH"`). Then let Codex workers read the worker skills:

```bash
bash <runway-agent clone>/setup/link-codex-skills.sh
```

(Clone `https://github.com/datacraftdevelopment/runway-agent` anywhere for `setup/`; re-run the link script and the `ln` line after each plugin update.)

Check: `bash setup/doctor.sh` passes on this machine.

## Step 6. Pair the workers (controller and each worker)

On **each worker**, in the Orca app: **Settings → Remote Orca Servers → Advertise this app as a server → New Link**. Connection address: its Tailscale address (`100.x.y.z`). **Generate Access Link** and copy it.

On **the controller**, in the Orca app: **Settings → Remote Orca Servers → Add Server**. Name it after the worker (this name is what `machines.json` calls `on`), paste the link, **Add Server**, then **Connect**.

The person does the clicking and the copying; you name the Macs and check. Check on the controller: `orca environment list --json` lists every worker as connected. Each worker Mac must stay awake while it has work: System Settings → Battery/Energy → prevent automatic sleeping when the display is off (on a desktop Mac), or keep it plugged in and open.

## Step 7. The repo on every machine

For each repo the loop will work on:

1. Clone it on the controller and on every worker (same remote; any folder). In Orca on each machine, add it as a project (**Add repo**), so Orca can make worktrees in it.
2. On each worker, find the repo selector Orca uses for it: `orca repo list --json` on that worker (or `orca repo list --json --environment <name>` from the controller). It goes in `machines.json` under that worker's `repos`, keyed by the repo's folder name.
3. On the default branch, commit a `runway.json` (template: the plugin's `templates/runway/runway.json`) with the repo's real test command as `check_cmd`.

## Step 8. The controller's machine list

```bash
mkdir -p ~/.pm-runway
cp "$(dirname "$(readlink -f ~/.local/bin/runway)")/../templates/runway/machines.json" ~/.pm-runway/machines.json
```

Edit it: one entry per Mac. The controller has `"on": null`; each worker has `"on": "<the name from step 6>"`. `slots` is how many tickets a Mac builds at once (1 on a laptop, 2 on a desktop Mac is a fair start); `max_running` caps the total. `builder` is the model that builds when a ticket says `any`; reviews always use a different one. The top-level `agents` list is the order work falls back through when an agent hits its usage limit. Remove a Mac's `agents` entries it can't run.

Check: `bash setup/doctor.sh --controller` passes.

## Step 9. The practice chunk (proves the whole loop)

`setup/practice/` is a tiny Python repo with a spec and three tickets: two independent (they should run at once, on different Macs) and one blocked by both.

1. Create a new **private** repo from it in the person's GitHub account and push (ask for the name; `gh repo create <name> --private --source <copy of setup/practice> --push`). Keep `runway.json` on main.
2. Clone it on every machine and add it in Orca (step 7); add its selector to each worker's `repos`.
3. On the controller, from the repo's root:

   ```bash
   runway check docs/maps/practice/tickets
   runway start docs/maps/practice/tickets
   ```

4. Ask the person to open a terminal tab **inside Orca** in that repo and run `runway loop --chunk practice`, and to open `runway board`'s URL in an Orca browser tab beside it.

What should happen, in order: practice-01 and practice-03 start on two different Macs; each is reviewed by the other model; both land on `chunk/practice`; practice-02 starts; it lands; a whole-chunk review runs; a PR from `chunk/practice` to main opens; its GitHub Actions check runs; the gate merges it, because every ticket is low risk and nothing sensitive changed. If a reviewer raised the risk, the gate stops and the PR waits for the person instead, which is also correct.

If it stalls, `runway status` and `runway-ask` say where. Write down every step that didn't match this runbook (command, output, what you did instead) in a short report for the person: those notes are how this runbook gets fixed.

## What's still unproven

Written against Orca's source and docs (2026-10-23) before the first real run: the JSON receipts of `run-create`, `worker-start` and `check` (the loop reads ids tolerantly and stops loudly if it can't), reading a run's inbox from a plain terminal with `--run`, and `--on` plus `--repo` on a paired Mac. Step 9 is the test of all three.
