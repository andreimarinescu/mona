#!/usr/bin/env bash
#
# resign-branch.sh — replay an unsigned agent branch with every commit signed, right before a push.
#
#   tools/resign-branch.sh [-C <path>] [--dry-run] <base> [<branch>]
#   tools/resign-branch.sh [-C <path>] --drop-archive <branch>
#
# Spec: vault pilot_protocol/specs/cosift-phase2-plan.md §3.1. Exit codes: 2 usage, 3 refused
# (nothing changed), 4 replay stopped, 5 a post-check failed (4 and 5 restore every branch).
set -euo pipefail

EX_USAGE=2 EX_REFUSED=3 EX_REPLAY=4 EX_CHECK=5
W='' TMPWT='' SNAP=''

say() { printf 'resign: %s\n' "$*" >&2; }
usage() { sed -n '5,6p' "$0" | sed 's/^# *//' >&2; exit $EX_USAGE; }
refuse() { say "refused: $*"; exit $EX_REFUSED; }

cleanup() {
  [ -z "$SNAP" ] || rm -f "$SNAP"
  [ -z "$TMPWT" ] || git worktree remove --force "$TMPWT" 2>/dev/null || true
}
trap cleanup EXIT

worktree_of() {
  git worktree list --porcelain | awk -v ref="refs/heads/$1" '
    /^worktree /{wt=substr($0,10)} $0=="branch " ref {print wt; exit}'
}

in_progress() {
  (cd "$W" && [ -e "$(git rev-parse --git-path rebase-merge)" ] || [ -e "$(git rev-parse --git-path rebase-apply)" ])
}

plan_range() {
  local -a shas=() subjects=()
  local line i j p found
  while IFS= read -r line; do shas+=("${line%% *}"); subjects+=("${line#* }"); done \
    < <(git log --reverse --format='%H %s' "$mb..$branch")
  S=0
  for i in "${!shas[@]}"; do
    case ${subjects[$i]} in
      'squash! '*|'amend! '*) refuse "${shas[$i]:0:12} is a squash!/amend! commit; only fixup! folds" ;;
      'fixup! '*)
        p=${subjects[$i]#fixup! } found=''
        for ((j = 0; j < i; j++)); do
          if [[ ${subjects[$j]} == "$p"* ]] || [[ $p =~ ^[0-9a-f]{4,40}$ && ${shas[$j]} == "$p"* ]]; then found=1; break; fi
        done
        [ -n "$found" ] || refuse "${shas[$i]:0:12} (${subjects[$i]}) targets a commit outside $mb..$branch"
        ;;
      *) S=$((S + 1)) ;;
    esac
  done
}

identities() {
  local c
  for c in $(git rev-list --reverse "$1"); do
    case $(git log -1 --format=%s "$c") in 'fixup! '*) continue ;; esac
    git log -1 --format='%an%x00%ae%x00%ad%x00%B' --date=raw "$c" | sha256sum
  done | sha256sum | cut -d' ' -f1
}

snapshot_refs() { git for-each-ref --format='%(refname) %(objectname)' refs/heads > "$SNAP"; }

restore_refs() {
  local ref sha
  while read -r ref sha; do
    [ "$(git rev-parse -q --verify "$ref" || true)" = "$sha" ] || git update-ref "$ref" "$sha"
  done < "$SNAP"
  git -C "$W" reset -q --hard
}

unfinished() {
  refuse "an unfinished rebase in $W: if a re-sign was interrupted, run git -C \"$W\" rebase --abort (the branch ref is intact until a replay ends), then retry"
}

fail() {
  local code=$1; shift
  say "FAILED: $*"
  if in_progress; then git -C "$W" rebase --abort || true; fi
  restore_refs
  say "restored $branch to ${old:0:12}; nothing was signed that survives"
  exit "$code"
}

check_tree() { [ "$(git rev-parse "$1^{tree}")" = "$oldtree" ]; }

check_signatures() {
  local c
  for c in $(git rev-list "$mb..$1"); do
    git verify-commit "$c" >/dev/null 2>&1 || return 1
    [ "$(git log -1 --format=%G? "$c")" = G ] || return 1
  done
}

check_moved_refs() {
  local ref sha now
  while read -r ref sha; do
    now=$(git rev-parse -q --verify "$ref" || true)
    [ "$now" = "$sha" ] && continue
    [ "$sha" != "$mb" ] && git merge-base --is-ancestor "$mb" "$sha" && git merge-base --is-ancestor "$sha" "$old" || return 1
    [ -n "$now" ] && [ "$(git rev-parse "$now^{tree}")" = "$(git rev-parse "$sha^{tree}")" ] || return 1
  done < "$SNAP"
}

replay() {  # fold unsigned, then sign each survivor once: one pass signs every pick and fixup amend
  (cd "$W" && GIT_SEQUENCE_EDITOR=true GIT_EDITOR=true \
    git -c commit.gpgsign=false rebase -q -i --autosquash --force-rebase --no-gpg-sign --update-refs "$mb") \
    || fail $EX_REPLAY "the fold stopped (conflict)"
  (cd "$W" && git rebase -q --force-rebase --gpg-sign --update-refs "$mb") \
    || fail $EX_REPLAY "the signing pass stopped (signing failure)"
}

drop_archive() {
  [ $# -eq 1 ] || usage
  local b=$1 arch="refs/archive/unsigned/$1"
  git rev-parse -q --verify "$arch" >/dev/null || refuse "no $arch"
  [ "$(git rev-parse -q --verify "refs/remotes/origin/$b" || true)" = "$(git rev-parse "refs/heads/$b")" ] \
    || refuse "origin/$b does not match the signed $b yet; push first"
  git update-ref -d "$arch"
  say "dropped $arch"
}

main() {
  local dry='' base new total unpushed fx ids
  if [ "${1:-}" = -C ]; then [ $# -ge 2 ] || usage; cd "$2"; shift 2; fi
  case ${1:-} in
    --drop-archive) shift; drop_archive "$@"; return ;;
    --dry-run) dry=1; shift ;;
  esac
  [ $# -ge 1 ] && [ $# -le 2 ] || usage
  base=$1
  W=$(git rev-parse --show-toplevel 2>/dev/null || true)
  [ -z "$W" ] || ! in_progress || unfinished
  branch=${2:-$(git symbolic-ref --short -q HEAD || true)}
  [ -n "$branch" ] || refuse "no branch given and HEAD is detached"
  git rev-parse -q --verify "refs/heads/$branch" >/dev/null || refuse "no local branch $branch"
  git rev-parse -q --verify "$base^{commit}" >/dev/null || refuse "unknown base $base"

  mb=$(git merge-base "$base" "$branch") || refuse "$branch and $base share no history"
  [ "$(git rev-parse "$base^{commit}")" = "$mb" ] \
    || say "note: $branch forks from ${mb:0:12}, behind $base; replaying in place (the tree must stay identical)"
  total=$(git rev-list --count "$mb..$branch")
  [ "$total" -gt 0 ] || refuse "nothing to replay: $branch has no commits over $base"
  [ -z "$(git rev-list --merges "$mb..$branch")" ] || refuse "$mb..$branch contains merge commits"
  unpushed=$(git rev-list --count "$mb..$branch" --not --remotes)
  [ "$unpushed" = "$total" ] || refuse "$((total - unpushed)) commit(s) in the range are already on a remote"
  plan_range

  W=$(worktree_of "$branch")
  if [ -n "$W" ]; then
    ! in_progress || unfinished
    git -C "$W" diff --quiet && git -C "$W" diff --cached --quiet || refuse "$W has uncommitted changes"
  fi
  old=$(git rev-parse "refs/heads/$branch")
  oldtree=$(git rev-parse "$old^{tree}")

  say "repo:    $(git rev-parse --path-format=absolute --git-common-dir)"
  say "branch:  $branch at ${old:0:12}${W:+ (checked out in $W)}"
  say "replay:  $total commit(s) over ${mb:0:12}; $((total - S)) fixup(s) fold"
  say "sign:    $S commit(s) = $S signature(s), each a YubiKey PIN + touch"
  [ -z "$dry" ] || { say "dry run: nothing changed"; return; }

  if [ -z "$W" ]; then
    TMPWT=$(mktemp -d /tmp/resign-wt.XXXXXX)
    git worktree add -q "$TMPWT" "$branch"
    W=$TMPWT
  fi
  ids=$(identities "$mb..$old")
  SNAP=$(mktemp /tmp/resign-refs.XXXXXX)
  snapshot_refs
  trap 'fail $EX_REPLAY "interrupted"' INT TERM
  if [ -z "${SSH_ASKPASS:-}" ] && [ -x "$HOME/.local/bin/ssh-askpass-zenity" ]; then
    export SSH_ASKPASS="$HOME/.local/bin/ssh-askpass-zenity" SSH_ASKPASS_REQUIRE=force
  fi

  replay

  new=$(git rev-parse "refs/heads/$branch")
  check_tree "$new" || fail $EX_CHECK "the replayed tree differs from ${oldtree:0:12}"
  [ "$(git rev-list --count "$mb..$new")" = "$S" ] || fail $EX_CHECK "expected $S commits after folding"
  fx=$(git log --format=%s "$mb..$new" | grep -cE '^(fixup|squash|amend)! ' || true)
  [ "$fx" = 0 ] || fail $EX_CHECK "$fx fixup!/squash!/amend! subject(s) survived"
  check_signatures "$new" || fail $EX_CHECK "a commit in the range is not validly signed"
  [ "$(identities "$mb..$new")" = "$ids" ] || fail $EX_CHECK "an author, author date or message changed"
  check_moved_refs || fail $EX_CHECK "a branch moved that the replay should not have touched"

  trap - INT TERM
  git update-ref "refs/archive/unsigned/$branch" "$old"
  git log --format='  %h %G? %s' "$mb..$new" >&2
  say "done: $branch is signed; the unsigned tip is kept as refs/archive/unsigned/$branch"
  say "next: git push origin $branch, then tools/resign-branch.sh --drop-archive $branch"
}

main "$@"
