#!/usr/bin/env bash
# Every apt download on the runner goes through ~/apt-debs, which actions/cache keeps between runs.
set -euo pipefail
if [ "${1:-}" = done ]; then
  sudo rm -rf ~/apt-debs/partial ~/apt-debs/lock
  sudo chown -R "$(id -u):$(id -g)" ~/apt-debs
  exit 0
fi
sudo rm -f /var/lib/man-db/auto-update
mkdir -p ~/apt-debs/partial
printf 'Dir::Cache::Archives "%s/apt-debs/";\nAPT::Keep-Downloaded-Packages "true";\nBinary::apt::APT::Keep-Downloaded-Packages "true";\n' "$HOME" |
  sudo tee /etc/apt/apt.conf.d/99mona-cache >/dev/null
