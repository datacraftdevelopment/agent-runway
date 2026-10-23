#!/bin/bash
# Regression tests for credential-guard.sh. Run from anywhere:
#   bash pm-runway/hooks/test-credential-guard.sh
# Each case simulates the PreToolUse Bash payload. block = exit 2, allow = exit 0.
# Cases 2, 3, 4, 5, 6 are the bypasses found in the 2026-08-28 review panel.
set -u
HOOK="$(cd "$(dirname "$0")" && pwd)/credential-guard.sh"
pass=0; fail=0

run_hook() { # $1 = command string; runs in current dir
  python3 -c 'import json,sys; print(json.dumps({"tool_input":{"command":sys.argv[1]}}))' "$1" \
    | bash "$HOOK" >/dev/null 2>&1
}

check() { # $1 = desc, $2 = block|allow, $3 = command
  run_hook "$3"
  local rc=$?
  local want=0; [ "$2" = block ] && want=2
  if [ "$rc" -eq "$want" ]; then
    pass=$((pass+1)); echo "  ok   [$2] $1"
  else
    fail=$((fail+1)); echo "  FAIL [$2, got rc=$rc] $1 :: $3"
  fi
}

tmp=$(mktemp -d) && cd "$tmp" || exit 1
git init -q
git config user.email t@example.com; git config user.name t

# Fixtures
echo secret > .env
echo readme > README.md
echo example > .env.example
mkdir somedir Secrets cleandir "sub repo"
echo secret > somedir/.env
echo token > Secrets/token.txt
echo clean > cleandir/notes.md
echo secret > "sub repo/.env"
echo '{}' > credentials.json
git add README.md credentials.json 2>/dev/null; git commit -qm init
echo changed > credentials.json   # modified tracked credential for -am case

echo "— blocks (each was a bypass or core case) —"
check "plain add of .env"                       block "git add .env"
check "add-then-commit chain"                   block "git add .env && git commit -m test"
check "git stage synonym"                       block "git stage .env"
check "directory operand hides nested .env"     block "git add somedir"
check "case-variant secrets dir"                block "git add Secrets/token.txt"
check "quoted -C path with spaces"              block "git -C \"$tmp/sub repo\" add .env"
check "add -A sweeps untracked .env"            block "git add -A"
check "add . sweeps untracked .env"             block "git add ."
check "commit -am picks up modified credential" block "git commit -am wip"
check "git mv then add in one command"          block "git mv README.md docs-readme.md && git add .env"
check "real git pipeline still blocked"         block "cd cleandir | cat; git add .env"
check "multi-line command"                      block "echo hi
git add .env"

git add .env 2>/dev/null || git add -f .env
check "pipeline that stages, even a safe file"   block "git log --oneline | head -1; git add README.md"
check "add piped"                               block "git add README.md | cat"
check "xargs feeds git add"                     block "printf README.md | xargs git add"
check "shell-wrapped git in a pipeline"         block "git status | sh -c 'git add .env'"
check "stage piped"                             block "git stage README.md | cat"
check "backgrounded commit"                     block "git commit -m x &"
check "commit with staged .env"                 block "git commit -m x"
git reset -q .env

echo "— allows —"
check "plain safe add"                          allow "git add README.md"
check "example file allowed"                    allow "git add .env.example"
check "clean directory operand"                 allow "git add cleandir"
check "commit with nothing secret staged"       allow "git commit -m x"
check "non-git command"                         allow "echo hello"
check "git without add/commit"                  allow "git status && git log --oneline"
check "git mv is index-only, allowed"           allow "git mv README.md docs-readme.md"
check "read-only subcommand added in 0.22.3"    allow "git show-ref"
check ".git in a non-git pipeline"              allow "grep -rn readme --exclude-dir=.git . | head"
check "read-only git piped (0.2.1)"             allow "git status | head -5"
check "read-only git -C piped"                  allow "git -C \"$tmp\" log --oneline | head -3"
check "diff piped to tail"                      allow "git diff --stat | tail -1"
check "ls-files piped twice"                    allow "git ls-files | sed -n 1p | wc -l"
check "read-only git with -c, piped"            allow "git -c core.quotepath=off ls-files | wc -l"
check "two read-only git in one pipeline"       allow "git log --oneline | head -1 && git status --short | cat"
check "git inside a grep pattern, piped"        allow "grep -rn \"git log\" . | head"
check "a bare git argument still means wrapped" block "printf x | grep git"
check "read-only git backgrounded"              allow "git status &"
check "non-staging git piped (0.28.3)"          allow "git stash | cat"
check "worktree list piped"                     allow "git worktree list | head"
check "remote get-url piped"                    allow "git remote get-url origin | cat"
check "read-only git -C with a variable (#118)"  allow "git -C \"\$REPO\" show HEAD:README.md"
check "read-only git -C with a substitution"     allow "git -C \"\$(git rev-parse --show-toplevel)\" log --oneline -3"
check "read-only git with unquoted range"        allow "git log \$BASE..HEAD --oneline"
check "read-only git --no-pager, piped"          allow "git --no-pager log --oneline | head -3"
check "read-only git with a pager config"        block "git -c core.pager='git add .env' -C \"\$REPO\" log"
check "read-only git with GIT_PAGER set"         block "GIT_PAGER='git add .env' git log"
check "add with a variable -C still blocked"     block "git -C \"\$REPO\" add ."
check "add after --no-pager still inspected"     block "git --no-pager add .env"
check "dynamic global option (Fable #1)"       block "OPT=-config-env=diff.external=X; git -\"\$OPT\" diff HEAD"
check "unquoted dynamic global option"           block "git -\$OPT log"
check "dynamic option via substitution"          block "git -\"\$(printf -- -config-env=core.pager=X)\" log"
check "exec-path before a read-only call"        block "git --exec-path=/tmp log"
check "unquoted substitution in -C (Astra #1)"   block "git -C \$(printf '. commit -a -m') status"
check "unquoted variable in -C"                  block "git -C \$DIR log"
check "unquoted variable in --work-tree"         block "git --work-tree \$D status"
check "variable in -c"                           block "git -c user.\$CFG log"
check "attached -c runs a command (Astra #2)"    block "git -cdiff.external='git add -f .env; true' diff --ext-diff"
check "grep -O opens a pager command"            block "git grep -O'git add -f .env #' x"
check "grep --open-files abbreviation"           block "git grep --open-files='git add .env' x"
check "brace expansion in -C"                    block "git -C {.,commit,-am} log"
check "plain grep still allowed"                 allow "git grep -n readme"

cd /
notrepo=$(mktemp -d) && cd "$notrepo"
touch .env
check "outside a git repo (fail-open)"          allow "git add .env"

cd /; rm -rf "$tmp" "$notrepo"
echo
echo "passed: $pass  failed: $fail"
[ "$fail" -eq 0 ]
