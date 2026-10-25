---
name: setup
description: "Set Runway up on this Mac from inside an agent session: check the tools and sign-ins Runway needs and walk the person through each fix, then watch a first repo with its check command. Use when the person says 'set up Runway', 'runway setup', 'is Runway ready', or Runway's setup screen sent them here. With 'join': add another Mac as a runner (not available yet)."
---

# Set up Runway

The Runway app's setup screen does the same checks. This is that, from inside an agent. Use `runway` on PATH, or
`/Applications/Runway.app/Contents/Resources/cli/bin/runway` (Runway.app must be installed first). Run each command on its own
(no `&&`, `||` or `;`: a session with an allow-list refuses chained commands).

## 1. Check this Mac

```bash
runway doctor
```

It lists git, gh, tmux, claude and codex, then the Claude Code, Codex and GitHub sign-ins, each with `ok`, `NO` and
the line that fixes it, or `--` for an engine that is optional because the other one is ready.

- **Tools:** show each missing tool's fix line and offer to run it. Run an install only when the person says yes.
- **Sign-ins:** the person signs in themselves (`claude auth login`, `codex login`, `gh auth login` open a browser or
  ask for a code). Never type, ask for or handle a password, token or key. Wait for them to say they're done.
- Run `runway doctor` again until it says ready. **One engine is enough**: Claude Code or Codex, installed and
  signed in. The other shows as optional; don't push the person to add it. With two, Runway prefers the other engine
  for the code review; with one, both reviews run on it in fresh sessions, and low-risk tickets still merge on their
  own.

## 2. runway in Terminal (optional)

If doctor says `runway in Terminal` is missing, offer `runway install-command`. It adds one link,
`~/.local/bin/runway`, and refuses to replace anything already there. If that folder isn't on PATH, it prints the line
to add it; show it and let the person decide.

## 3. A first repo

Ask which repo, as a local clone of a GitHub repo. Suggest one only from what the person mentions; don't pick for them.

```bash
runway repo suggest-check <path>    # the name, the GitHub repo, and a guessed check command
runway repo add <path> --check "<the test command>"
```

Confirm the check command with the person: it runs before every pull request and must pass for a ticket to merge.
A repo with a `runway.json` on its base branch can set `check_cmd` there instead, which wins.

Then they can file tickets from a normal session with the file-tickets skill.

## join: another Mac

Not available yet. Runway runs tickets on this Mac only in this version; other Macs as runners (over SSH) come
next. Say so if asked, and don't add or change anything on another Mac.
