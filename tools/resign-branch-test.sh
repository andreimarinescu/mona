#!/usr/bin/env bash
#
# resign-branch-test.sh — exercise tools/resign-branch.sh on scratch repos with a throwaway key.
#
#   tools/resign-branch-test.sh             run every case
#   tools/resign-branch-test.sh --mutants   then prove each guard is load-bearing
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
SUT=${SUT:-$HERE/resign-branch.sh}
ROOT=$(mktemp -d /tmp/resign-test.XXXXXX)
trap 'rm -rf "$ROOT"' EXIT

export HOME="$ROOT/home" GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL="$ROOT/gitconfig"
unset SSH_ASKPASS SSH_ASKPASS_REQUIRE GIT_DIR GIT_WORK_TREE
mkdir -p "$HOME"
ssh-keygen -q -t ed25519 -N '' -C resign-test -f "$ROOT/key"
ssh-keygen -q -t ed25519 -N '' -C resign-stranger -f "$ROOT/stranger"
cat > "$ROOT/sign" <<EOF
#!/bin/sh
case " \$* " in *" -Y sign "*) echo x >> "$ROOT/sign-calls"
  [ -z "\${SLOW_SIGN:-}" ] || { : > "$ROOT/signing"; sleep "\$SLOW_SIGN"; } ;; esac
exec ssh-keygen "\$@"
EOF
chmod +x "$ROOT/sign"
echo "test@example.com namespaces=\"git\" $(cat "$ROOT/key.pub")" > "$ROOT/allowed_signers"
cat > "$GIT_CONFIG_GLOBAL" <<EOF
[user]
	name = Test Author
	email = test@example.com
	signingkey = $ROOT/key
[gpg]
	format = ssh
[gpg "ssh"]
	allowedSignersFile = $ROOT/allowed_signers
	program = $ROOT/sign
[commit]
	gpgsign = false
[init]
	defaultBranch = main
EOF

PASS=0 FAIL=0 N=0 CLOCK=1700000000 CASE='' R='' D='' OUT='' RC=''

new_repo() {
  N=$((N + 1)) R="$ROOT/c$N" D="$ROOT/c$N/repo"
  git init -q --bare "$R/origin.git"
  git init -q "$D"
  commit base.txt base "base"
  git -C "$D" remote add origin "$R/origin.git"
  git -C "$D" push -q origin main
  git -C "$D" switch -q -c work
}

commit() {  # file content subject — in $D, with a distinct author date
  CLOCK=$((CLOCK + 60))
  printf '%s\n' "$2" > "$D/$1"
  git -C "$D" add "$1"
  GIT_AUTHOR_DATE="@$CLOCK +0200" git -C "$D" commit -q -m "$3"
}

fixup() {  # file content target-rev
  CLOCK=$((CLOCK + 60))
  printf '%s\n' "$2" > "$D/$1"
  git -C "$D" add "$1"
  GIT_AUTHOR_DATE="@$CLOCK +0200" git -C "$D" commit -q --fixup="$3"
}

run() { : > "$ROOT/sign-calls"; set +e; OUT=$("$SUT" -C "$D" "$@" 2>&1); RC=$?; set -e; }
signs() { wc -l < "$ROOT/sign-calls" | tr -d ' '; }

check() {
  local name=$1; shift
  if "$@"; then PASS=$((PASS + 1)); else FAIL=$((FAIL + 1)); echo "FAIL: $CASE: $name (rc=$RC)" >&2; [ -z "${VERBOSE:-}" ] || printf '%s\n' "$OUT" >&2; fi
}

g() { git -C "$D" "$@"; }
eq() { [ "$1" = "$2" ]; }
rc() { [ "$RC" = "$1" ]; }
said() { grep -qE -- "$1" <<<"$OUT"; }
tip() { g rev-parse "refs/heads/$1"; }
tree() { g rev-parse "$1^{tree}"; }
count() { g rev-list --count "$1"; }
clean() { git -C "${1:-$D}" diff --quiet && git -C "${1:-$D}" diff --cached --quiet; }
no_archive() { ! g rev-parse -q --verify "refs/archive/unsigned/$1" >/dev/null; }
has_archive() { g rev-parse -q --verify "refs/archive/unsigned/$1" >/dev/null; }
no_rebase() { [ ! -e "$(git -C "$D" rev-parse --path-format=absolute --git-path rebase-merge)" ]; }
signed_all() { local c; for c in $(g rev-list "$1"); do [ "$(g log -1 --format=%G? "$c")" = G ] || return 1; done; }
unsigned_all() { local c; for c in $(g rev-list "$1"); do [ "$(g log -1 --format=%G? "$c")" = N ] || return 1; done; }
no_fixups() { ! g log --format=%s "$1" | grep -qE '^(fixup|squash|amend)! '; }
idents() { g log --reverse --format='%an|%ae|%ad|%s' --date=raw "$1" | grep -v '|fixup! ' || true; }

case_happy() {
  CASE=happy; new_repo
  commit a.txt a1 "add a"; commit b.txt b1 "add b"; commit c.txt c1 "add c"
  fixup a.txt a2 "$(g rev-parse HEAD~2)"
  local old oldtree before; old=$(tip work) oldtree=$(tree work) before=$(idents main..work)
  run main
  check "exit 0" rc 0
  check "touch count printed" said 'sign: +3 commit'
  check "3 commits" eq "$(count main..work)" 3
  check "all signed" signed_all main..work
  check "one signature per surviving commit" eq "$(signs)" 3
  check "tree identical" eq "$(tree work)" "$oldtree"
  check "no fixup subjects" no_fixups main..work
  check "authors, dates, subjects kept" eq "$(idents main..work)" "$before"
  check "archive ref" eq "$(g rev-parse refs/archive/unsigned/work)" "$old"
  check "archive not under refs/heads" eq "$(g for-each-ref --format=x refs/heads/archive)" ""
  check "clean" clean
}

case_dry_run() {
  CASE=dry-run; new_repo
  commit a.txt a1 "add a"; commit b.txt b1 "add b"
  local old; old=$(tip work)
  run --dry-run main
  check "exit 0" rc 0
  check "touch count printed" said 'sign: +2 commit'
  check "unchanged" eq "$(tip work)" "$old"
  check "still unsigned" unsigned_all main..work
  check "no archive" no_archive work
}

case_pushed() {
  CASE=already-pushed; new_repo
  commit a.txt a1 "add a"; g push -q origin work; commit b.txt b1 "add b"
  local old; old=$(tip work)
  run main
  check "refused" rc 3
  check "names the remote" said 'already on a remote'
  check "unchanged" eq "$(tip work)" "$old"
  check "no archive" no_archive work
}

case_republish() {
  CASE=republish; new_repo
  commit a.txt a1 "add a"; g push -q origin work; commit b.txt b1 "add b"
  local old; old=$(tip work)
  run --republish main
  check "succeeds" rc 0
  check "says it rewrites pushed commits" said 'already on a remote get rewritten'
  check "tree unchanged" eq "$(g rev-parse "work^{tree}")" "$(g rev-parse "$old^{tree}")"
  check "both signed" eq "$(g log --format=%G? main..work | sort -u | tr -d '\n')" "G"
  check "archive kept" eq "$(g rev-parse refs/archive/unsigned/work)" "$old"
}

case_merge() {
  CASE=merge; new_repo
  commit a.txt a1 "add a"
  g switch -q -c side main; commit s.txt s1 "add s"; g switch -q work
  g merge -q --no-ff side -m "merge side"
  local old; old=$(tip work)
  run main
  check "refused" rc 3
  check "names the merge" said 'merge commits'
  check "unchanged" eq "$(tip work)" "$old"
}

case_fixup_outside() {
  CASE=fixup-outside-range; new_repo
  commit a.txt a1 "add a"; fixup base.txt base2 main
  local old; old=$(tip work)
  run main
  check "refused" rc 3
  check "names the fixup" said 'targets a commit outside'
  check "unchanged" eq "$(tip work)" "$old"
}

case_squash() {
  CASE=squash; new_repo
  commit a.txt a1 "add a"
  printf 'a2\n' > "$D/a.txt"; g add a.txt; g commit -q --squash=HEAD --no-edit
  run main
  check "refused" rc 3
  check "names squash" said 'squash!/amend!'
}

case_conflict() {
  CASE=conflicting-fixup; new_repo
  commit f.txt x "set x"; commit f.txt y "set y"
  fixup f.txt z "$(g rev-parse HEAD~1)"
  local old; old=$(tip work)
  run main
  check "exit 4" rc 4
  check "restored" eq "$(tip work)" "$old"
  check "no rebase left" no_rebase
  check "clean" clean
  check "still unsigned" unsigned_all main..work
  check "no archive" no_archive work
}

case_bad_key() {
  CASE=signer-not-allowed; new_repo
  commit a.txt a1 "add a"; commit b.txt b1 "add b"
  g config user.signingkey "$ROOT/stranger"
  local old oldtree; old=$(tip work) oldtree=$(tree work)
  run main
  check "exit 5" rc 5
  check "names the signature" said 'not validly signed'
  check "restored" eq "$(tip work)" "$old"
  check "HEAD on work" eq "$(g symbolic-ref HEAD)" refs/heads/work
  check "worktree at old tree" eq "$(g write-tree)" "$oldtree"
  check "clean" clean
  check "no archive" no_archive work
}

case_tampered_tree() {
  CASE=tampered-tree; new_repo
  commit a.txt a1 "add a"; commit b.txt b1 "add b"
  cat > "$D/.git/hooks/post-rewrite" <<'EOF'
#!/bin/sh
[ "$1" = rebase ] || exit 0
echo tampered > tamper.txt && git add tamper.txt && git commit -q --amend -S --no-edit
EOF
  chmod +x "$D/.git/hooks/post-rewrite"
  local old; old=$(tip work)
  run main
  check "exit 5" rc 5
  check "names the tree" said 'tree differs'
  check "restored" eq "$(tip work)" "$old"
  check "tamper file gone" test ! -e "$D/tamper.txt"
  check "no archive" no_archive work
}

case_tampered_ref() {
  CASE=tampered-ref; new_repo
  g branch other main
  commit a.txt a1 "add a"
  cat > "$D/.git/hooks/post-rewrite" <<'EOF'
#!/bin/sh
[ "$1" = rebase ] && git update-ref refs/heads/other "$(git commit-tree -m moved HEAD^{tree})"
EOF
  chmod +x "$D/.git/hooks/post-rewrite"
  local old other; old=$(tip work) other=$(tip other)
  run main
  check "exit 5" rc 5
  check "names the moved branch" said 'branch moved'
  check "work restored" eq "$(tip work)" "$old"
  check "other restored" eq "$(tip other)" "$other"
  check "no archive" no_archive work
}

case_stacked() {
  CASE=stacked; new_repo
  commit a.txt a1 "add a"; commit b.txt b1 "add b"; g branch lower; commit c.txt c1 "add c"
  local lowertree; lowertree=$(tree lower)
  run main
  check "exit 0" rc 0
  check "lower re-signed" signed_all main..lower
  check "lower tree identical" eq "$(tree lower)" "$lowertree"
  check "lower still 2 commits" eq "$(count main..lower)" 2
  check "lower under work" g merge-base --is-ancestor lower work
}

case_unfinished() {
  CASE=unfinished; new_repo
  commit a.txt a1 "add a"; commit b.txt b1 "add b"
  local old; old=$(tip work)
  GIT_SEQUENCE_EDITOR="sed -i 1s/^pick/edit/" g rebase -q -i main >/dev/null 2>&1
  run main
  check "exit 3" rc 3
  check "names the unfinished rebase" said 'unfinished rebase.*rebase --abort'
  run main work
  check "exit 3 with a branch" rc 3
  check "names it with a branch" said 'unfinished rebase'
  check "branch untouched" eq "$(tip work)" "$old"
  g rebase --abort
}

case_interrupt() {
  CASE=interrupt; new_repo
  commit a.txt a1 "add a"; commit b.txt b1 "add b"
  fixup a.txt a2 "$(g rev-parse HEAD~1)"
  local old pid; old=$(tip work)
  rm -f "$ROOT/signing"
  SLOW_SIGN=20 setsid "$SUT" -C "$D" main > "$ROOT/int.out" 2>&1 &
  pid=$!
  for _ in $(seq 100); do [ -e "$ROOT/signing" ] && break; sleep 0.1; done
  kill -INT -- -"$pid"
  set +e; wait "$pid"; RC=$?; set -e
  OUT=$(cat "$ROOT/int.out")
  check "exit 4" rc 4
  check "restored" eq "$(tip work)" "$old"
  check "HEAD on work" eq "$(g symbolic-ref --short -q HEAD)" work
  check "no rebase left" no_rebase
  check "still unsigned" unsigned_all main..work
  check "no archive" no_archive work
}

case_terminate() {  # TERM to the script alone: the rebase child runs on, so only the trap can restore
  CASE=terminate; new_repo
  commit a.txt a1 "add a"; commit b.txt b1 "add b"
  fixup a.txt a2 "$(g rev-parse HEAD~1)"
  local old pid; old=$(tip work)
  rm -f "$ROOT/signing"
  SLOW_SIGN=1 "$SUT" -C "$D" main > "$ROOT/term.out" 2>&1 &
  pid=$!
  for _ in $(seq 100); do [ -e "$ROOT/signing" ] && break; sleep 0.1; done
  kill -TERM "$pid"
  set +e; wait "$pid"; RC=$?; set -e
  for _ in $(seq 150); do no_rebase && break; sleep 0.1; done
  sleep 1
  check "exit 4" rc 4
  check "restored" eq "$(tip work)" "$old"
  check "no rebase left" no_rebase
  check "no archive" no_archive work
}

case_other_worktree() {
  CASE=agent-worktree; new_repo
  g switch -q main
  g config extensions.worktreeConfig true
  g config commit.gpgsign true
  g worktree add -q -b agent "$R/wt" main
  git -C "$R/wt" config --worktree commit.gpgsign false
  local keep=$D; D="$R/wt"
  commit a.txt a1 "add a"; commit b.txt b1 "add b"
  check "agent commits unsigned" unsigned_all main..agent
  D=$keep
  run main agent
  check "exit 0" rc 0
  check "signed" signed_all main..agent
  check "main checkout untouched" eq "$(g symbolic-ref HEAD)" refs/heads/main
  check "agent worktree on agent" eq "$(git -C "$R/wt" rev-parse HEAD)" "$(tip agent)"
  check "agent worktree clean" clean "$R/wt"
}

case_base_advanced() {
  CASE=base-advanced; new_repo
  commit a.txt a1 "add a"; commit b.txt b1 "add b"
  local fork oldtree; fork=$(g rev-parse main) oldtree=$(tree work)
  g switch -q main; commit m.txt m1 "main moves"; g push -q origin main; g switch -q work
  run main
  check "exit 0" rc 0
  check "notes it" said 'behind main'
  check "tree identical" eq "$(tree work)" "$oldtree"
  check "still on the old fork point" eq "$(g rev-parse work~2)" "$fork"
}

case_not_checked_out() {
  CASE=not-checked-out; new_repo
  commit a.txt a1 "add a"; g switch -q main
  run main work
  check "exit 0" rc 0
  check "signed" signed_all main..work
  check "temp worktree removed" eq "$(g worktree list | wc -l)" 1
  check "HEAD still main" eq "$(g symbolic-ref HEAD)" refs/heads/main
}

case_drop_archive() {
  CASE=drop-archive; new_repo
  commit a.txt a1 "add a"
  run main
  check "exit 0" rc 0
  run --drop-archive work
  check "refused before push" rc 3
  check "archive kept" has_archive work
  g push -q origin work
  run --drop-archive work
  check "dropped after push" rc 0
  check "archive gone" no_archive work
}

case_dirty() {
  CASE=dirty; new_repo
  commit a.txt a1 "add a"; printf 'edit\n' > "$D/a.txt"
  run main
  check "refused" rc 3
  check "names it" said 'uncommitted changes'
}

case_nothing() {
  CASE=nothing; new_repo
  run main
  check "refused" rc 3
  check "names it" said 'nothing to replay'
}

for c in happy dry_run pushed republish merge fixup_outside squash conflict bad_key tampered_tree tampered_ref stacked \
         unfinished interrupt terminate other_worktree base_advanced not_checked_out drop_archive dirty nothing; do
  "case_$c"
done
echo "resign-branch tests: $PASS passed, $FAIL failed"

if [ "${1:-}" = --mutants ] && [ "$FAIL" = 0 ]; then
  survived=0
  mutant() {
    local m="$ROOT/mutant-$1.sh"
    sed '$d' "$SUT" > "$m"
    printf '%s\nmain "$@"\n' "$2" >> "$m"
    chmod +x "$m"
    if SUT="$m" "$0" >/dev/null 2>&1; then echo "mutant SURVIVED: $1"; survived=1; else echo "mutant killed: $1"; fi
  }
  mutant tree-check 'check_tree() { return 0; }'
  mutant signature-check 'check_signatures() { return 0; }'
  mutant restore 'restore_refs() { :; }'
  mutant moved-refs-check 'check_moved_refs() { return 0; }'
  mutant fixup-scope 'plan_range() { S=$(git rev-list --count "$mb..$branch"); }'
  mutant interrupt-trap 'trap() { :; }'
  mutant unfinished-diagnosis 'unfinished() { refuse "HEAD is detached"; }'
  mutant one-pass-replay 'replay() { (cd "$W" && GIT_SEQUENCE_EDITOR=true GIT_EDITOR=true git rebase -q -i --autosquash --force-rebase --gpg-sign --update-refs "$mb") || fail $EX_REPLAY "the replay stopped"; }'
  [ "$survived" = 0 ] || exit 1
fi
[ "$FAIL" = 0 ]
