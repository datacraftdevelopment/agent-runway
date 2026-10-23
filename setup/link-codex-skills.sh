#!/bin/bash
# Let Codex workers load pm-runway's worker skills. Codex reads skills from ~/.codex/skills;
# Claude Code reads them from the plugin. Re-run after each plugin update.
set -e
root=$(find "$HOME/.claude/plugins" -path '*pm-runway*/.claude-plugin/plugin.json' -type f 2>/dev/null | sort | tail -1)
[ -n "$root" ] || { echo "pm-runway is not installed in Claude Code yet"; exit 1; }
root=$(dirname "$(dirname "$root")")
mkdir -p "$HOME/.codex/skills"
for s in work-ticket review-ticket tdd code-review codebase-design ship-acceptance; do
  ln -sfn "$root/skills/$s" "$HOME/.codex/skills/$s"
  echo "linked $s"
done
