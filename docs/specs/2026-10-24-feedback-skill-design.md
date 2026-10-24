# Feedback skill: file an issue on the public repo from any session

Status: design, 2026-10-24. Small; ships with the Runway skills (Phase 3 of `docs/plans/2026-10-23-runway-app.md`).
The skill text below is ready to drop in as `skills/feedback/SKILL.md` once the plugin folder exists.

## Why

Runway is handed to people who will hit rough edges. The cheapest feedback path is the session they are already in:
they say what went wrong, their agent writes a clear issue with the facts a maintainer needs, and files it on
`datacraftdevelopment/runway-agent`. The website and the issue forms (`.github/ISSUE_TEMPLATE/`) cover people
who never install the skills.

## Decisions

- **Files only on the person's go**, typed in that session, after they have seen the full title and body. Same rule
  as `file-tickets`.
- **The repo is public, so the draft is scrubbed before it is shown.** No tokens, keys, private repo names or paths,
  hostnames, machine names, client names or code from the person's own repos. Home paths become `~`. The person is
  told the issue will be public.
- **Facts gathered, not asked:** Runway version (`runway --version`), macOS (`sw_vers -productVersion`), which agents
  are installed and signed in (`runway doctor --json` if present), and the last error line from the loop if the
  person is reporting a failed run. Anything that can't be read is left out, never guessed.
- **One issue per report**, labelled `bug` or `enhancement` to match the issue forms.
- **Filing path, in order:** `gh issue create -R datacraftdevelopment/runway-agent` when `gh` is signed in; otherwise
  a prefilled `https://github.com/datacraftdevelopment/runway-agent/issues/new?title=…&body=…&labels=…` URL opened
  in the browser for the person to submit (so no GitHub sign-in is ever needed by the agent). Long bodies (over
  about 6,000 characters URL-encoded) are cut to the essentials and the rest pasted by the person.
- **Search before filing:** `gh issue list -R … --search` on two or three key words; if a match looks like the same
  problem, offer to add a comment there instead.

## Acceptance

- [ ] A1: In a Claude Code session with the Runway skills, `/runway:feedback the board froze after I closed the lid`
  shows a draft with title, body, version and macOS filled in, and files nothing until the person types go.
  Verify: the session transcript, then the new issue on GitHub.
- [ ] A2: The same in Codex files an equivalent issue. Verify: the issue.
- [ ] A3: With `gh` signed out, the skill opens a prefilled new-issue page instead of failing. Verify: the browser tab.
- [ ] A4: A draft built from a session whose working folder is a private repo shows no path, repo name or code from
  it. Verify: read the draft and the filed issue.

## Skill text

```markdown
---
name: feedback
description: File a bug report or idea about Runway itself on its public GitHub repo. Use when the person says something about Runway is broken, confusing or missing and wants to tell its makers, or runs /runway:feedback.
---

# Feedback for Runway

The person wants to tell Runway's makers about a bug or an idea. You draft one GitHub issue on
datacraftdevelopment/runway-agent, show it, and file it only on their go.

1. Read what they said. If it is unclear whether it is a bug or an idea, or what they expected, ask one question.
2. Gather facts without asking: `runway --version`, `sw_vers -productVersion`, `runway doctor --json` (agents and
   sign-ins), and for a failed run the last error line `runway status --json` shows. Skip whatever fails.
3. Search for an existing issue: `gh issue list -R datacraftdevelopment/runway-agent --state all --search "<2-3 words>"`.
   If one matches, show it and offer a comment on it instead of a new issue.
4. Draft: a title under 70 characters; body sections What happened (or What I want), Steps, Expected, Facts
   (version, macOS, agents). Label `bug` or `enhancement`.
5. Scrub the draft. The repo is PUBLIC. Remove tokens, keys, passwords, hostnames, machine names, client or company
   names, private repo names, and any code or file contents from the person's own repos. Replace home paths with `~`.
6. Show the whole draft and say: "This will be public on GitHub. File it?" Wait for a go typed in this session.
   Anything else is not a go.
7. On go: `gh issue create -R datacraftdevelopment/runway-agent --title … --body-file … --label …`. If `gh` is missing
   or not signed in, open
   `https://github.com/datacraftdevelopment/runway-agent/issues/new?title=<enc>&body=<enc>&labels=<label>` with
   `open` and tell them to press Submit. Reply with the issue link (or that the page is open).
```
