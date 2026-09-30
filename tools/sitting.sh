#!/usr/bin/env bash
#
# sitting.sh — one signing sitting: ask the operator (zenity), sign every unpushed commit on a branch, push, verify.
#
#   tools/sitting.sh [-C <repo>] [--dry-run] [--remote <name>] [<branch>]    (branch defaults to main)
#
# Exit codes: 0 pushed, 2 usage, 3 declined or refused (nothing changed), 4 stopped after failed attempts.
set -euo pipefail

EX_USAGE=2 EX_DECLINED=3 EX_FAILED=4 TRIES=3
HERE=$(cd "$(dirname "$0")" && pwd)
RESIGN=${SITTING_RESIGN:-$HERE/resign-branch.sh}
ZENITY=${SITTING_ZENITY:-zenity}
TITLE="Mona signing sitting"
remote=origin dry='' CP='' SSHHOST='' branch='' base=''

say() { printf 'sitting: %s\n' "$*" >&2; }
usage() { sed -n '5p' "$0" | sed 's/^# *//' >&2; exit $EX_USAGE; }
ask() { "$ZENITY" --question --no-wrap --title="$TITLE" --text="$1" 2>/dev/null; }
tell() { "$ZENITY" --info --no-wrap --title="$TITLE" --text="$1" 2>/dev/null || true; }
again() {
  "$ZENITY" --question --no-wrap --title="$TITLE" --ok-label=Retry --cancel-label=Stop --text="$1 did not go through (attempt $2 of $TRIES): a missed PIN or touch?

Three wrong PINs in a row lock the YubiKey until it is unplugged and plugged back in." 2>/dev/null
}
stop() { say "stopped: $*"; tell "Stopped: $*"; exit "${2:-$EX_FAILED}"; }

sign_once() {  # a fold conflict is not a missed PIN: stop instead of offering a retry
  local out rc=0
  out=$("$RESIGN" "$base" "$branch" 2>&1) || rc=$?
  printf '%s\n' "$out" >&2
  if [ $rc -ne 0 ] && printf '%s' "$out" | grep -q 'fold stopped'; then
    stop "the fixup fold conflicts; nothing was signed" $EX_DECLINED
  fi
  return $rc
}

close_master() { [ -z "$CP" ] || ssh -o ControlPath="$CP" -O exit "$SSHHOST" >/dev/null 2>&1 || true; }
trap close_master EXIT

attempt() {  # attempt <label> <cmd...>: run, and on failure offer a retry up to TRIES times
  local label=$1 n=1; shift
  until "$@"; do
    [ "$n" -lt "$TRIES" ] && again "$label" "$n" || return 1
    n=$((n + 1))
  done
}

setup_ssh() {
  local url host
  url=$(git remote get-url --push "$remote")
  case $url in
    ssh://*) host=${url#ssh://}; host=${host%%/*}; host=${host%%:*} ;;
    *@*:*) host=${url%%:*} ;;
    *) return 0 ;;
  esac
  SSHHOST=$host
  CP="${XDG_RUNTIME_DIR:-/tmp}/sitting-ssh-%C"
  export GIT_SSH_COMMAND="ssh -o ControlMaster=auto -o ControlPersist=600 -o ControlPath=$CP"
  if [ -z "${SSH_ASKPASS:-}" ] && [ -x "$HOME/.local/bin/ssh-askpass-gui" ]; then
    export SSH_ASKPASS="$HOME/.local/bin/ssh-askpass-gui" SSH_ASKPASS_REQUIRE=force
  fi
}

main() {
  if [ "${1:-}" = -C ]; then [ $# -ge 2 ] || usage; cd "$2"; shift 2; fi
  while [ $# -gt 0 ]; do
    case $1 in
      --dry-run) dry=1 ;;
      --remote) [ $# -ge 2 ] || usage; remote=$2; shift ;;
      -*) usage ;;
      *) break ;;
    esac
    shift
  done
  [ $# -le 1 ] || usage
  local tip n sigs list plan from
  branch=${1:-main}
  base="refs/remotes/$remote/$branch"
  git rev-parse -q --verify "refs/heads/$branch" >/dev/null || stop "no local branch $branch" $EX_USAGE
  git rev-parse -q --verify "$base" >/dev/null || stop "no $remote/$branch yet; the first push is manual" $EX_USAGE
  tip=$(git rev-parse "refs/heads/$branch")
  n=$(git rev-list --count "$base..$branch")
  [ "$n" -gt 0 ] || { say "nothing to sign: $branch has no commits over $remote/$branch"; exit 0; }

  plan=$("$RESIGN" --dry-run "$base" "$branch" 2>&1) || stop "$(printf '%s' "$plan" | tail -1)" $EX_DECLINED
  sigs=$(printf '%s\n' "$plan" | sed -n 's/^resign: sign: *\([0-9]*\) commit.*/\1/p')
  list=$(git log --reverse --format='  • %s' "$base..$branch" | grep -v '^  • fixup! ' | head -20)
  say "plan: $sigs signature(s) for $n commit(s) on $branch, then push to $remote"
  [ -z "$dry" ] || { printf '%s\n%s\n' "$plan" "$list" >&2; exit 0; }

  local conn=0
  [ -z "$(git remote get-url --push "$remote" | grep -E '^(ssh://|[^/]*@[^/]*:)' || true)" ] || conn=1
  ask "Sign and push $branch of $(basename "$(git rev-parse --show-toplevel)")?

$sigs signature(s) for $n commit(s), then push to $remote.
You'll be asked for the YubiKey PIN and a touch $((sigs + conn)) time(s)$([ $conn = 0 ] || echo " ($conn for the GitHub connection)").

$list" || { say "declined by the operator; nothing changed"; exit $EX_DECLINED; }

  setup_ssh
  attempt "Connecting to $remote" git fetch -q "$remote" "$branch" || stop "could not reach $remote; nothing was signed"
  git merge-base --is-ancestor "$base" "$branch" \
    || stop "$remote/$branch moved and is not an ancestor of $branch; reconcile first, nothing was signed" $EX_DECLINED
  [ "$(git rev-parse "refs/heads/$branch")" = "$tip" ] || stop "$branch moved during the sitting; nothing was signed" $EX_DECLINED
  from=$(git rev-parse "$base")

  attempt "Signing" sign_once || stop "signing failed; $branch is restored unsigned at ${tip:0:12}"
  attempt "Pushing to $remote" git push -q "$remote" "$branch" \
    || stop "push failed; $branch is signed locally, retry with: git push $remote $branch"

  [ "$(git rev-parse "$base")" = "$(git rev-parse "refs/heads/$branch")" ] || stop "$remote/$branch does not match $branch after the push"
  [ -z "$(git log --format='%G?' "$from..$branch" | grep -v '^G$' || true)" ] || stop "a pushed commit is not validly signed"
  say "done: $branch pushed signed; the unsigned tip ${tip:0:12} stays at refs/archive/unsigned/$branch"
  say "lanes based on it: git rebase --onto $branch refs/archive/unsigned/$branch <lane>, then $RESIGN --drop-archive $branch"
  tell "Pushed $branch: $sigs signed commit(s)."
}

main "$@"
