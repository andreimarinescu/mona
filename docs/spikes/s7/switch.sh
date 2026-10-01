#!/usr/bin/env bash
# Install one S7 configuration into the mona-s7 Hermes profile and restart Hermes.
#   A: today's config (deploy/hermes as committed)
#   B: the skills toolset on, curated recipes only (no bundled catalog), self-authoring staged
#   B0: B plus the bundled catalog the profile already holds (prompt-size probe only)
#   C: today's config, the same recipes appended to SOUL.md
#   D: A without Hermes' model-gated tool-use enforcement and execution-discipline blocks (extra)
#   CD: C plus D's two keys (extra)
set -euo pipefail

cfg=${1:?usage: switch.sh A|B|B0|C|D|CD}
ROOT=$(cd "$(dirname "$(readlink -f "$0")")/../../.." && pwd)
HERE=$ROOT/docs/spikes/s7
SNAP=$ROOT/data/snapshots/demo-prefiled/hermes
read -r -a COMPOSE <<<"${MONA_COMPOSE:-docker compose -p mona-s7}"
STAGE=$(mktemp -d /tmp/s7-stage-XXXX)
trap 'rm -rf "$STAGE"' EXIT

cp "$ROOT/deploy/hermes/config.yaml" "$STAGE/config.yaml"
cp "$ROOT/deploy/hermes/SOUL.md" "$STAGE/SOUL.md"
case "$cfg" in
  A) ;;
  B | B0)
    sed -i 's/^  api_server: \[memory, mona\]$/  api_server: [memory, skills, mona]/' "$STAGE/config.yaml"
    sed -i 's/^  project_discovery: false$/  project_discovery: false\n  guard_agent_created: true/' "$STAGE/config.yaml"
    grep -q 'api_server: \[memory, skills, mona\]' "$STAGE/config.yaml"
    grep -q 'guard_agent_created: true' "$STAGE/config.yaml"
    mkdir -p "$STAGE/skills/mona"
    cp -r "$HERE/recipes/." "$STAGE/skills/mona/"
    ;;
  C | D | CD)
    if [[ $cfg == C* ]]; then
      "$ROOT/apps/api/.venv/bin/python" "$HERE/s7_probe.py" soul-c >>"$STAGE/SOUL.md"
    fi
    if [[ $cfg == *D ]]; then
      sed -i 's/^  max_turns: 12$/  max_turns: 12\n  tool_use_enforcement: false\n  execution_guidance: false/' "$STAGE/config.yaml"
      grep -q 'execution_guidance: false' "$STAGE/config.yaml"
    fi
    ;;
  *) echo "unknown config $cfg" >&2; exit 2 ;;
esac

"${COMPOSE[@]}" stop -t 30 hermes >/dev/null
"${COMPOSE[@]}" run --rm --no-deps -T \
  -v "$STAGE:/s7:ro" -v "$SNAP:/snap:ro" -e S7_CFG="$cfg" \
  --entrypoint sh hermes-seed -c '
set -e
H=/opt/data
install -m 640 -o 1000 -g 1000 /s7/config.yaml $H/config.yaml
install -m 644 -o 1000 -g 1000 /s7/SOUL.md $H/SOUL.md
rm -rf $H/memories && cp -r /snap/memories $H/memories && chown -R 1000:1000 $H/memories
rm -rf $H/skills/mona $H/.skills_prompt_snapshot.json
if [ "$S7_CFG" = B ] || [ "$S7_CFG" = B0 ]; then
  cp -r /s7/skills/mona $H/skills/mona && chown -R 1000:1000 $H/skills/mona
fi
if [ "$S7_CFG" = B0 ]; then
  rm -f $H/.no-bundled-skills
  for d in /snap/skills/*/; do n=$(basename "$d"); [ -e "$H/skills/$n" ] || cp -r "$d" "$H/skills/$n"; done
  chown -R 1000:1000 $H/skills
else
  touch $H/.no-bundled-skills && chown 1000:1000 $H/.no-bundled-skills
  find $H/skills -mindepth 1 -maxdepth 1 -type d ! -name mona -exec rm -rf {} +
fi
echo "skills on disk: $(find $H/skills -name SKILL.md | wc -l)"
' 2>&1 | grep -v 'Container\|Creating\|Created'
"${COMPOSE[@]}" start hermes >/dev/null
for _ in $(seq 60); do
  [[ "$("${COMPOSE[@]}" ps --format '{{.Health}}' hermes)" == healthy ]] && { echo "hermes healthy ($cfg)"; exit 0; }
  sleep 2
done
echo "hermes not healthy" >&2
exit 1
