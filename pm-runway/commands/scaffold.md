---
description: Scaffold a project from the pm-runway starter — client engagement, personal project, or in-place _pm/ for an existing folder — and run the skeleton interview. Also adds a stack's plugins to a repo (`stack vercel`).
argument-hint: <ClientName> | self <ProjectName> | here | stack <name>…
---

# /pm-runway:scaffold

Stand up a project from the bundled starter. The starter is **deliberately
minimal** — only day-one files; every other folder is created on first write
(the taxonomy in the stamped `CLAUDE.md` is the map). Moves, in order:
**copy → rename → git → orient**. Don't skip the interview.

The argument is: **$ARGUMENTS**

## 1. Resolve the mode and name

Four modes — read the argument (and the user's phrasing) to pick one:

| Mode | Trigger | Target |
|---|---|---|
| **Client** (default) | A bare name: `Acme` | `datacraft-<ClientName>/` |
| **Personal** | `self` / `personal` / "for me" / "no client", plus a name: `self HomeLab` | `<ProjectName>/` — no prefix; `datacraft-` is reserved for client work |
| **In-place** | `here`, `.`, "this folder" | `_pm/` + `docs/` wiring added to the current directory |
| **Stack** | `stack`, alone or with names: `stack vercel supabase`, "add the Vercel stack" | Only step 5b, in the current directory. Works on a repo that is already scaffolded and on one that never was |

- If `$ARGUMENTS` is empty, ask ONE question: *"What are we standing up? A client name (→ `datacraft-<Client>/`), a personal project (`self <Name>` → plain `<Name>/`), or `here` to add `_pm/` to this folder."* **A missing client is never a blocker** — personal and in-place modes don't have one.
- Normalise the name to a folder-safe token (strip spaces/punctuation, keep it readable — "Acme Corp" → `AcmeCorp`).
- New-folder modes create the target **in the current working directory**. If the target folder already exists, stop and tell the user — don't overwrite.
- In-place mode: if `./_pm/` already exists, stop — this folder is already scaffolded.

## 2. Copy the template

The starter lives inside this plugin.

**Client / personal** — copy it wholesale (it's minimal now — this creates no ballast):

```bash
cp -R "${CLAUDE_PLUGIN_ROOT}/template/." "./<TargetFolder>/"
find "./<TargetFolder>" -name .DS_Store -delete
```

**In-place** — copy ONLY `_pm/`; the copy step touches nothing else that
already exists (step 5 makes small, additive edits — that's its contract,
not this step's):

```bash
cp -R "${CLAUDE_PLUGIN_ROOT}/template/_pm" "./_pm"
find "./_pm" -name .DS_Store -delete
```

The session skills (`whats-next`, `stepping-away`, `checkpoint`, …) ship
globally with this plugin — never copy them into the project.

**Never pre-create taxonomy folders** (`_pm/transcripts/`, `resources/`,
`knowledge/`, …). They're documented in the stamped `CLAUDE.md` and get
created the first time something is written into them.

## 3. Rename the placeholder

*(Skip for in-place.)* In the **copied** files:

- `CLAUDE.md`: replace the "This is a STARTER" banner block with a one-line
  project header naming the client (or personal project) and today's date.
  **Personal mode:** where a line reads wrong without a client
  ("engagement"), soften to "project" — touch only the lines that read
  wrong. Leave the rest intact.
- `README.md`: set the title to the project name.

## 4. Git

First check `python3 --version` reports 3.9 or newer. The credential guard
and the session helpers need it; if it's missing or older, say so and stop
before any git or session step.

The workflow's first artifacts (design docs in `docs/specs/` from
`brainstorming`, plans in `docs/plans/`) are *committed* files, so the
project must be a repository.

- **New-folder modes:** if the target is not already inside a git worktree,
  `git init` it and make one baseline commit of the scaffold
  (`chore: scaffold from pm starter`). If it IS inside an existing worktree
  (e.g. a monorepo), say so and skip the init.
- **In-place mode:** don't init anything — but if the folder isn't a git
  repo, tell the user plainly that brainstorming, the plans and the
  credential-guard hook all assume one, and ask whether to `git init`.

## 5. Wire the shared record

- **No empty folders.** `docs/specs/`, `docs/plans/`, `docs/maps/` and
  `docs/adr/` are created the first time something is written into them
  (brainstorming, writing-plans, wayfinder, domain-modeling).
- **The tracker — local markdown by default (0.17).** The template ships
  `docs/agents/issue-tracker.md` preset to the local-markdown
  convention, with maps in `docs/maps/`; `/pm-runway:wayfinder` reads it, for
  the rare foggy effort. Ask no tracker question. In-place mode: copy it from
  `${CLAUDE_PLUGIN_ROOT}/template/docs/agents/issue-tracker.md` **only if
  absent** — an existing file is that repo's decision, never overwritten. Say
  in the sign-off that a team repo can use GitHub Issues instead: copy
  `${CLAUDE_PLUGIN_ROOT}/templates/issue-tracker-github.md` over it.
- **The inbox.** `docs/inbox.md` ships in the template (loose ideas, one
  line each, no status). In-place mode: copy it if absent, same rule.
- **`.gitignore`** — the template's covers new-folder modes. In-place mode:
  ensure `.env`, `account.md`, `_pm/transcripts/`, `.worktrees/` and `.superpowers/` (the
  plan ledgers and brainstorming mockups) are ignored (append
  additively; pm-runway's `credential-guard` hook blocks staging them, but the
  ignore is the belt to that brace).
- **Verification block** — the template `CLAUDE.md` already carries
  `## Verifying your work`. In-place mode: if `CLAUDE.md` exists without
  that section, or without `## How we work`, append those sections from
  `${CLAUDE_PLUGIN_ROOT}/template/CLAUDE.md`; if there is no `CLAUDE.md` at
  all, create a minimal one (project one-liner + those sections) and say
  you did.

**In-place mutation contract:** the additive edits above (`.gitignore`
lines, `CLAUDE.md` section, `docs/` stubs, and step 5b's `enabledPlugins`
entries in `.claude/settings.json`) are the ONLY changes allowed
outside `_pm/`; never rewrite or reorganize existing content, and name every
touched file in the sign-off.

## 5b. Stacks — the plugins this repo needs

Plugins for one kind of work (Vercel, Supabase, FileMaker) are kept out of
the global setup and enabled per repo. The table is
`${CLAUDE_PLUGIN_ROOT}/stacks.json`; edit that file to change what a stack
gets, never this command.

1. See which stacks the repo looks like (new-folder modes: run it in the
   target folder; a fresh scaffold usually detects nothing, so ask instead):

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/stacks.py" --root . detect
   ```

2. Name what was detected, or the stacks the user asked for, and get a yes.
   One question, and "none" is a fine answer. `stacks.py list` shows the
   table. In Stack mode with names given, the names are the yes.

3. Apply the stacks the user confirmed:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/stacks.py" --root . apply vercel supabase
   ```

   It adds the stack's plugins to `.claude/settings.json` under
   `enabledPlugins` and changes nothing else. A plugin the repo already
   lists, on or off, stays as the repo has it. Run again, it changes
   nothing.

4. Relay the result: what was added, what was already there, anything kept
   disabled, any `notes`, and the `install_commands`. **Do not run the
   install commands yourself** — hand them to the user, one per fenced block.
   A machine that doesn't have a plugin yet needs its command run once; the
   new plugins load in the next session.

In a Claude Code Project (cloud threads), a repo's declared plugins do not
load. Say so when the user mentions threads, and point them at Project
settings > Plugins.

**Stack mode ends here**: skip the interview, and sign off with step 4's
relay and the files touched (`.claude/settings.json` only).

## 6. Run the skeleton interview

`_pm/skeleton.md` is the default planning artifact (Wei Hao's 5-step) —
every mode gets one. Don't leave it as a placeholder — interview the user,
briefly. Ask these one at a time, conversationally, and keep it short (a
change-request job only needs a paragraph):

1. **Outcome sentence** — when this project is done, what's true that wasn't before?
2. **Critical user journey** — the one path through the deliverable that has to work.
3. **Minimum capabilities** — the few things that path requires. (Only what would *break the journey* if removed.)
4. **Fundamental enablers** — what has to exist underneath (data, access, integrations)?
5. **Non-negotiables** — hard constraints (deadline, budget, tech, compliance).

Write the answers into `_pm/skeleton.md` in that 5-step structure. If the
user says it's a small job, collapse it to a single tight paragraph — the
artifact scales with content.

## 7. Sign off

Confirm what you did in 3–4 lines: what was created (new folder or in-place
`_pm/`), git state (initialized / existing / declined), renames done,
skeleton captured, tracker preset (local) and inbox present, stacks applied (or none), and — in-place —
every file touched. Then point at the next step: *"Brainstorm the first piece
of work — it writes a design doc in `docs/specs/` with its acceptance checks.
Then `whats-next` when you start a working session."*

Don't start doing project work — scaffolding ends here.
