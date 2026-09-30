#!/usr/bin/env bash
#
# sitting-test.sh — exercise tools/sitting.sh on scratch repos with a throwaway key, a fake zenity and a local bare remote.
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
SUT=${SUT:-$HERE/sitting.sh}
ROOT=$(mktemp -d /tmp/sitting-test.XXXXXX)
trap 'rm -rf "$ROOT"' EXIT

export HOME="$ROOT/home" GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL="$ROOT/gitconfig"
unset SSH_ASKPASS SSH_ASKPASS_REQUIRE GIT_DIR GIT_WORK_TREE GIT_SSH_COMMAND
mkdir -p "$HOME"
ssh-keygen -q -t ed25519 -N '' -C sitting-test -f "$ROOT/key"
cat > "$ROOT/sign" <<EOF
#!/bin/sh
case " \$* " in *" -Y sign "*)
  echo x >> "$ROOT/sign-calls"
  if [ -n "\${FAIL_SIGNS:-}" ] && [ "\$(wc -l < "$ROOT/sign-calls")" -le "\$FAIL_SIGNS" ]; then exit 1; fi ;;
esac
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
cat > "$ROOT/zenity" <<EOF
#!/bin/sh
echo "\$*" >> "$ROOT/zenity-log"
case " \$* " in
  *" --ok-label=Retry "*) exit "\${RETRY_ANSWER:-0}" ;;
  *" --question "*) exit "\${ASK_ANSWER:-0}" ;;
esac
exit 0
EOF
chmod +x "$ROOT/zenity"
export SITTING_ZENITY="$ROOT/zenity"

pass=0 fail=0
ok() { pass=$((pass + 1)); }
bad() { fail=$((fail + 1)); printf 'FAIL: %s\n' "$*" >&2; }
check() { if eval "$2"; then ok; else bad "$1"; fi; }

fresh() {  # a repo with main pushed (one signed-looking base) plus 3 unsigned commits and a fixup
  rm -rf "$ROOT/r" "$ROOT/remote.git" "$ROOT/sign-calls" "$ROOT/zenity-log"
  git init -q --bare "$ROOT/remote.git"
  git init -q "$ROOT/r"
  cd "$ROOT/r"
  git remote add origin "$ROOT/remote.git"
  echo base > f; git add f; git commit -q -m base; git push -q origin main
  for i in 1 2 3; do echo "$i" > "f$i"; git add "f$i"; git commit -q -m "change $i"; done
  echo fix >> f2; git commit -q -am "fixup! change 2"
  : > "$ROOT/sign-calls"; : > "$ROOT/zenity-log"
}
calls() { wc -l < "$ROOT/sign-calls" | tr -d ' '; }
remote_tip() { git --git-dir="$ROOT/remote.git" rev-parse main; }
run() { set +e; "$SUT" "$@" >"$ROOT/out" 2>&1; rc=$?; set -e; }

fresh; tip=$(git rev-parse main); rt=$(remote_tip)
run --dry-run
check "dry run exits 0" '[ $rc = 0 ]'
check "dry run plans 3 signatures" 'grep -q "3 signature" "$ROOT/out"'
check "dry run asks nothing" '[ ! -s "$ROOT/zenity-log" ]'
echo dirty >> f1; run --dry-run; git checkout -q f1
check "a refused dry run shows no dialog" '[ $rc = 3 ] && [ ! -s "$ROOT/zenity-log" ]'
check "dry run leaves main" '[ "$(git rev-parse main)" = "$tip" ]'

fresh; tip=$(git rev-parse main); rt=$(remote_tip)
ASK_ANSWER=1 run
check "declined exits 3" '[ $rc = 3 ]'
check "declined signs nothing" '[ "$(calls)" = 0 ]'
check "declined leaves main" '[ "$(git rev-parse main)" = "$tip" ]'
check "declined leaves the remote" '[ "$(remote_tip)" = "$rt" ]'
check "permission text names the signature count" 'grep -q "3 signature" "$ROOT/zenity-log"'

fresh; tip=$(git rev-parse main)
run
check "accepted exits 0" '[ $rc = 0 ]'
check "one signature per surviving commit" '[ "$(calls)" = 3 ]'
check "remote equals main" '[ "$(remote_tip)" = "$(git rev-parse main)" ]'
check "every pushed commit is signed" '[ -z "$(git log --format=%G? origin/main~3..origin/main | grep -v "^G$")" ]'
check "the fixup folded" '[ "$(git rev-list --count origin/main~3..origin/main)" = 3 ] && ! git log --format=%s origin/main | grep -q "^fixup!"'
check "the tree is unchanged" '[ "$(git rev-parse main^{tree})" = "$(git rev-parse "$tip^{tree}")" ]'
check "the unsigned tip is archived" '[ "$(git rev-parse refs/archive/unsigned/main)" = "$tip" ]'

fresh
FAIL_SIGNS=1 run
check "a missed signature is retried and then succeeds" '[ $rc = 0 ] && [ "$(remote_tip)" = "$(git rev-parse main)" ]'
check "the retry was offered once" '[ "$(grep -c -- "--ok-label=Retry" "$ROOT/zenity-log")" = 1 ]'

fresh; tip=$(git rev-parse main); rt=$(remote_tip)
FAIL_SIGNS=100 run
check "exhausted retries exit 4" '[ $rc = 4 ]'
check "exhausted retries offer 2 retries" '[ "$(grep -c -- "--ok-label=Retry" "$ROOT/zenity-log")" = 2 ]'
check "exhausted retries restore main unsigned" '[ "$(git rev-parse main)" = "$tip" ]'
check "exhausted retries leave the remote" '[ "$(remote_tip)" = "$rt" ]'

fresh; tip=$(git rev-parse main); rt=$(remote_tip)
FAIL_SIGNS=1 RETRY_ANSWER=1 run
check "stop at the retry prompt exits 4" '[ $rc = 4 ] && [ "$(git rev-parse main)" = "$tip" ] && [ "$(remote_tip)" = "$rt" ]'

fresh; tip=$(git rev-parse main)
git clone -q "$ROOT/remote.git" "$ROOT/other"
(cd "$ROOT/other" && echo other > g && git add g && git commit -q -m other && git push -q origin main)
rm -rf "$ROOT/other"
run
check "a moved remote is refused" '[ $rc = 3 ] && [ "$(calls)" = 0 ] && [ "$(git rev-parse main)" = "$tip" ]'

fresh; tip=$(git rev-parse main)
echo 2b > f2; git commit -q -am "change 2 again"; echo clash >> f2; git commit -q -am "fixup! change 2"
tip=$(git rev-parse main)
run
check "a conflicting fold stops without a retry prompt" '[ $rc = 3 ] && [ "$(git rev-parse main)" = "$tip" ] && ! grep -q -- "--ok-label=Retry" "$ROOT/zenity-log"'

fresh; signed_base=$(git rev-parse origin/main); git push -q origin main
echo more > f4; git add f4; git commit -q -m "change 4"; tip=$(git rev-parse main)
run --from "$signed_base"
check "republish exits 0" '[ $rc = 0 ]'
check "republish force-pushes: remote equals main" '[ "$(remote_tip)" = "$(git rev-parse main)" ]'
check "republish signs every commit above the base" '[ -z "$(git log --format=%G? "$signed_base..main" | grep -v "^G$")" ] && [ "$(git rev-list --count "$signed_base..main")" = 4 ]'
check "republish keeps the tree" '[ "$(git rev-parse main^{tree})" = "$(git rev-parse "$tip^{tree}")" ]'
check "republish warns about the rewrite in the permission text" 'grep -q "rewrites 4 commit" "$ROOT/zenity-log"'

fresh; signed_base=$(git rev-parse origin/main); git push -q origin main
squashed=$(git commit-tree -p "$signed_base" -m "changes 1-3" "$(git rev-parse main^{tree})"); git reset -q --hard "$squashed"
echo more > f4; git add f4; git commit -q -m "change 4"; tip=$(git rev-parse main)
run --from "$signed_base"
check "republish of folded pushed commits exits 0" '[ $rc = 0 ] && [ "$(remote_tip)" = "$(git rev-parse main)" ]'
check "republish of folded pushed commits signs 2" '[ "$(calls)" = 2 ] && [ "$(git rev-parse main^{tree})" = "$(git rev-parse "$tip^{tree}")" ]'

fresh; signed_base=$(git rev-parse origin/main); git push -q origin main
squashed=$(git commit-tree -p "$signed_base" -m "changes 1-3" "$(git rev-parse main^{tree})"); git reset -q --hard "$squashed"; tip=$(git rev-parse main)
git clone -q "$ROOT/remote.git" "$ROOT/other"
(cd "$ROOT/other" && echo other > g && git add g && git commit -q -m other && git push -q origin main)
rm -rf "$ROOT/other"; rt=$(remote_tip)
run --from "$signed_base"
check "republish refuses a remote that moved since the plan" '[ $rc = 3 ] && [ "$(calls)" = 0 ] && [ "$(git rev-parse main)" = "$tip" ] && [ "$(remote_tip)" = "$rt" ]'

fresh; git push -q origin main
run --from "$(git rev-parse main)"
check "--from at the tip has nothing to sign" '[ $rc = 0 ] && [ ! -s "$ROOT/zenity-log" ]'

fresh; git push -q origin main; other=$(git commit-tree -m stray "$(git rev-parse HEAD^{tree})")
run --from "$other"
check "--from outside the branch is refused" '[ $rc = 2 ]'

fresh; git push -q origin main
run
check "nothing to sign exits 0 without asking" '[ $rc = 0 ] && [ ! -s "$ROOT/zenity-log" ]'

printf 'sitting tests: %d passed, %d failed\n' "$pass" "$fail"
[ "$fail" = 0 ]
