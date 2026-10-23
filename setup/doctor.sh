#!/bin/bash
# pm-runway setup check. Run on every machine; add --controller on the one that runs the loop.
# Prints one line per check and exits non-zero if any required check failed. Changes nothing.
controller=0
[ "$1" = "--controller" ] && controller=1
fail=0
ok()   { printf '  ok    %s\n' "$1"; }
bad()  { printf '  FIX   %s\n        %s\n' "$1" "$2"; fail=1; }
warn() { printf '  note  %s\n        %s\n' "$1" "$2"; }
have() { command -v "$1" >/dev/null 2>&1; }

echo "Tools"
have git && ok "git $(git --version | awk '{print $3}')" || bad "git" "xcode-select --install"
if have python3 && python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))'; then
  ok "python3 $(python3 -c 'import platform; print(platform.python_version())')"
else
  bad "python3 3.9 or newer" "xcode-select --install, or brew install python"
fi
have gh && ok "gh" || bad "gh (GitHub CLI)" "brew install gh"
have gh && { gh auth status >/dev/null 2>&1 && ok "gh signed in" || bad "gh signed in" "gh auth login"; }

echo "Agents (your own subscriptions)"
have claude && ok "claude $(claude --version 2>/dev/null | head -1)" || bad "Claude Code CLI" "curl -fsSL https://claude.ai/install.sh | bash"
have codex && ok "codex $(codex --version 2>/dev/null | head -1)" || bad "Codex CLI" "brew install codex  (or: npm install -g @openai/codex)"
if have codex; then
  codex login status >/dev/null 2>&1 && ok "codex signed in" || bad "codex signed in" "codex login"
fi
[ -d "$HOME/.claude" ] && ok "~/.claude exists (claude has run here)" || bad "claude has never run here" "run claude once and sign in with /login"

echo "Orca and the network"
if have orca; then
  orca status --json >/dev/null 2>&1 && ok "orca answers" || bad "orca answers" "open the Orca app, then retry (orca open --json)"
else
  bad "orca CLI on PATH" "brew install --cask stablyai/orca/orca, open it, then Settings > General > Orca CLI"
fi
have tailscale && { tailscale status >/dev/null 2>&1 && ok "tailscale connected" || bad "tailscale connected" "open Tailscale and sign in"; } \
  || warn "tailscale CLI not found" "fine if the Tailscale app is installed and connected; otherwise brew install --cask tailscale"

echo "pm-runway"
plugin=$(find "$HOME/.claude/plugins" -path '*pm-runway*/bin/runway' -type f 2>/dev/null | sort | tail -1)
[ -n "$plugin" ] && ok "pm-runway plugin installed" || bad "pm-runway plugin" "claude plugin marketplace add datacraftdevelopment/dc-dev-plugins && claude plugin install pm-runway@dc-dev-plugins"
have runway && ok "runway on PATH" || bad "runway on PATH" "mkdir -p ~/.local/bin && ln -sf \"$plugin\" ~/.local/bin/runway  (and ~/.local/bin on PATH)"
for other in pm-sp pm; do
  find "$HOME/.claude/plugins" -maxdepth 4 -type d -name "$other" -path '*dc-dev-plugins*' 2>/dev/null | grep -q . \
    && warn "$other is in the plugin cache" "pm-runway replaces it: claude plugin uninstall $other@dc-dev-plugins (ignore if already uninstalled)"
done
for s in work-ticket review-ticket tdd code-review; do
  [ -e "$HOME/.codex/skills/$s" ] || { bad "Codex can read the $s skill" "run setup/link-codex-skills.sh"; break; }
done

if [ $controller = 1 ]; then
  echo "Controller"
  m="${PM_RUNWAY_HOME:-$HOME/.pm-runway}/machines.json"
  [ -f "$m" ] && python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$m" && ok "machines.json" \
    || bad "machines.json" "copy pm-runway's templates/runway/machines.json to $m and edit it"
  have orca && orca environment list --json >/dev/null 2>&1 && ok "orca environment list answers (paired Macs)" \
    || warn "no paired Macs listed" "pair each worker: SETUP-AGENT.md step 6"
fi

echo
[ $fail = 0 ] && echo "All required checks pass." || echo "Fix the FIX lines above, then run this again."
exit $fail
