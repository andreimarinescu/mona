#!/usr/bin/env bash
#
# sitting.sh — one signing sitting: ask the operator (zenity), sign every unpushed commit on a branch, push, verify.
#
#   tools/sitting.sh [-C <repo>] [--dry-run] [--remote <name>] [--from <signed commit>] [<branch>]    (branch defaults to main)
#   --from re-signs everything above that commit, including commits already pushed, and force-pushes with a lease.
#
# Exit codes: 0 pushed, 2 usage, 3 declined or refused (nothing changed), 4 stopped after failed attempts.
set -euo pipefail

EX_USAGE=2 EX_DECLINED=3 EX_FAILED=4 TRIES=3
HERE=$(cd "$(dirname "$0")" && pwd)
RESIGN=${SITTING_RESIGN:-$HERE/resign-branch.sh}
ZENITY=${SITTING_ZENITY:-zenity}
TITLE="Mona signing sitting"
remote=origin dry='' CP='' SSHHOST='' branch='' base='' rbase='' from_arg='' rflag=''

say() { printf 'sitting: %s\n' "$*" >&2; }
usage() { sed -n '5,6p' "$0" | sed 's/^# *//' >&2; exit $EX_USAGE; }
ask() { "$ZENITY" --question --no-wrap --title="$TITLE" --text="$1" 2>/dev/null; }
tell() { "$ZENITY" --info --no-wrap --title="$TITLE" --text="$1" 2>/dev/null || true; }
again() {
  "$ZENITY" --question --no-wrap --title="$TITLE" --ok-label=Retry --cancel-label=Stop --text="$1 did not go through (attempt $2 of $TRIES): a missed PIN or touch?

Three wrong PINs in a row lock the YubiKey until it is unplugged and plugged back in." 2>/dev/null
}
stop() { say "stopped: $1"; [ -n "$dry" ] || tell "Stopped: $1"; exit "${2:-$EX_FAILED}"; }

sign_once() {  # a fold conflict is not a missed PIN: stop instead of offering a retry
  local out rc=0
  out=$("$RESIGN" $rflag "$rbase" "$branch" 2>&1) || rc=$?
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
      --from) [ $# -ge 2 ] || usage; from_arg=$2; shift ;;
      -*) usage ;;
      *) break ;;
    esac
    shift
  done
  [ $# -le 1 ] || usage
  local tip n sigs list plan from rewritten=0 lease=''
  branch=${1:-main}
  base="refs/remotes/$remote/$branch"
  git rev-parse -q --verify "refs/heads/$branch" >/dev/null || stop "no local branch $branch" $EX_USAGE
  git rev-parse -q --verify "$base" >/dev/null || stop "no $remote/$branch yet; the first push is manual" $EX_USAGE
  tip=$(git rev-parse "refs/heads/$branch")
  rbase=$base
  if [ -n "$from_arg" ]; then
    rbase=$(git rev-parse -q --verify "$from_arg^{commit}") || stop "unknown commit $from_arg" $EX_USAGE
    git merge-base --is-ancestor "$rbase" "$branch" || stop "$from_arg is not an ancestor of $branch" $EX_USAGE
    git merge-base --is-ancestor "$rbase" "$base" || stop "$from_arg is not on $remote/$branch" $EX_USAGE
    rflag=--republish
    rewritten=$(git rev-list --count "$rbase..$base")
  fi
  n=$(git rev-list --count "$rbase..$branch")
  [ "$n" -gt 0 ] || { say "nothing to sign: $branch has no commits over ${from_arg:-$remote/$branch}"; exit 0; }

  plan=$("$RESIGN" --dry-run $rflag "$rbase" "$branch" 2>&1) || stop "$(printf '%s' "$plan" | tail -1)" $EX_DECLINED
  sigs=$(printf '%s\n' "$plan" | sed -n 's/^resign: sign: *\([0-9]*\) commit.*/\1/p')
  list=$(git log --reverse --format='  • %s' "$rbase..$branch" | grep -v '^  • fixup! ' | head -20)
  say "plan: $sigs signature(s) for $n commit(s) on $branch, then push to $remote"
  [ -z "$dry" ] || { printf '%s\n%s\n' "$plan" "$list" >&2; exit 0; }

  local conn=0
  [ -z "$(git remote get-url --push "$remote" | grep -E '^(ssh://|[^/]*@[^/]*:)' || true)" ] || conn=1
  ask "Sign and push $branch of $(basename "$(git rev-parse --show-toplevel)")?

$sigs signature(s) for $n commit(s), then push to $remote.$([ "$rewritten" = 0 ] || printf '\nThis rewrites %s commit(s) already on %s (a force push with lease).' "$rewritten" "$remote")
You'll be asked for the YubiKey PIN and a touch $((sigs + conn)) time(s)$([ $conn = 0 ] || echo " ($conn for the GitHub connection)").

$list" || { say "declined by the operator; nothing changed"; exit $EX_DECLINED; }

  local planned; planned=$(git rev-parse "$base")
  setup_ssh
  attempt "Connecting to $remote" git fetch -q "$remote" "$branch" || stop "could not reach $remote; nothing was signed"
  if [ -n "$from_arg" ]; then
    [ "$(git rev-parse "$base")" = "$planned" ] \
      || stop "$remote/$branch moved since the plan; reconcile first, nothing was signed" $EX_DECLINED
  else
    git merge-base --is-ancestor "$base" "$branch" \
      || stop "$remote/$branch moved and is not an ancestor of $branch; reconcile first, nothing was signed" $EX_DECLINED
  fi
  [ "$(git rev-parse "refs/heads/$branch")" = "$tip" ] || stop "$branch moved during the sitting; nothing was signed" $EX_DECLINED
  from=$(git rev-parse "$rbase")
  lease=$(git rev-parse "$base")

  attempt "Signing" sign_once || stop "signing failed; $branch is restored unsigned at ${tip:0:12}"
  local push=(git push -q "$remote" "$branch")
  [ "$rewritten" = 0 ] || push=(git push -q --force-with-lease="refs/heads/$branch:$lease" "$remote" "$branch")
  attempt "Pushing to $remote" "${push[@]}" \
    || stop "push failed; $branch is signed locally, retry with: git push $remote $branch"

  [ "$(git rev-parse "$base")" = "$(git rev-parse "refs/heads/$branch")" ] || stop "$remote/$branch does not match $branch after the push"
  [ -z "$(git log --format='%G?' "$from..$branch" | grep -v '^G$' || true)" ] || stop "a pushed commit is not validly signed"
  say "done: $branch pushed signed; the unsigned tip ${tip:0:12} stays at refs/archive/unsigned/$branch"
  say "lanes based on it: git rebase --onto $branch refs/archive/unsigned/$branch <lane>, then $RESIGN --drop-archive $branch"
  tell "Pushed $branch: $sigs signed commit(s)."
}

main "$@"
