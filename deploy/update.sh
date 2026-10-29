#!/usr/bin/env bash
# Safely update the radio code on the Pi:
#   deploy/update.sh            # latest origin/main
#   deploy/update.sh v1.2       # a tag or commit
# Fetches, checks out (detached), runs the self-check, restarts the service and
# confirms it stays up. On any failure it returns to the previous commit.
# Success tags the commit "known-good" for automatic crash-loop rollback.
#
# Everything is inside main() so bash has read the whole script before the
# checkout replaces this file on disk.
set -euo pipefail

main() {
  local repo ref previous target
  repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  ref="${1:-origin/main}"
  cd "$repo"

  previous="$(git rev-parse HEAD)"
  git fetch --tags --prune origin
  target="$(git rev-parse --verify "$ref^{commit}")"
  echo "== Updating ${previous:0:7} -> ${target:0:7} ($ref)"

  rollback() {
    echo "!! $1 - rolling back to ${previous:0:7}"
    git checkout --detach --quiet "$previous"
    sudo systemctl reset-failed radio || true
    sudo systemctl start radio
    exit 1
  }

  git checkout --detach --quiet "$target"
  sudo systemctl stop radio  # frees the audio device for the check
  echo "== Self-check"
  python3 -m radio --check || rollback "self-check failed"

  echo "== Restarting radio"
  sudo systemctl reset-failed radio || true
  sudo systemctl start radio
  sleep 15
  systemctl is-active --quiet radio || rollback "service is not running after restart"
  [ "$(git rev-parse HEAD)" = "$target" ] || rollback "service crashed and was rolled back"

  git tag -f known-good HEAD >/dev/null
  echo "== OK: radio running ${target:0:7}, tagged known-good"
  exit 0
}

main "$@"
