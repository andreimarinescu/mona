#!/usr/bin/env bash
# Expected sha256: 2nd argument, else VERSION (same version), else GitHub's asset digest.
set -euo pipefail

version="${1:?usage: scripts/vendor-pdfjs.sh <version> [sha256]}"
expected="${2:-}"
root="$(cd "$(dirname "$0")/.." && pwd)"
dest="$root/apps/web/public/pdfjs"
zip="pdfjs-${version}-dist.zip"
url="https://github.com/mozilla/pdf.js/releases/download/v${version}/${zip}"

if [[ -z "$expected" && -f "$dest/VERSION" ]] && grep -qx "version=${version}" "$dest/VERSION"; then
  expected="$(sed -n 's/^sha256=//p' "$dest/VERSION")"
fi
if [[ -z "$expected" ]]; then
  expected="$(curl -fsSL "https://api.github.com/repos/mozilla/pdf.js/releases/tags/v${version}" \
    | jq -r --arg name "$zip" '.assets[] | select(.name == $name) | .digest' | sed 's/^sha256://')"
fi
[[ "$expected" =~ ^[0-9a-f]{64}$ ]] || { echo "no sha256 for ${zip}" >&2; exit 1; }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
curl -fsSL -o "$tmp/$zip" "$url"
actual="$(sha256sum "$tmp/$zip" | cut -d' ' -f1)"
if [[ "$actual" != "$expected" ]]; then
  echo "sha256 mismatch for ${zip}: expected ${expected}, got ${actual}" >&2
  exit 1
fi

rm -rf "$dest"
mkdir -p "$dest"
unzip -q "$tmp/$zip" -d "$dest"
find "$dest" -name '*.map' -delete
rm -f "$dest/web/compressed.tracemonkey-pldi-09.pdf"
printf 'version=%s\nsha256=%s\nsource=%s\n' "$version" "$actual" "$url" > "$dest/VERSION"
echo "pdf.js ${version} vendored (sha256 ${actual})"
