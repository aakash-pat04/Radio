#!/bin/bash
# Installed as /usr/local/bin/radio-rollback (outside the repo, so a broken
# checkout cannot break its own recovery). Runs as root from radio-rollback.service.
#   radio-rollback <repo> <user>
set -u
repo="$1"
user="$2"
git_as_user() { runuser -u "$user" -- git -C "$repo" "$@"; }
log() { echo "radio-rollback: $*"; }

good=$(git_as_user rev-parse -q --verify 'refs/tags/known-good^{commit}') || {
  log "no known-good tag; leaving the checkout alone"
  exit 0
}
current=$(git_as_user rev-parse HEAD)
if [ "$current" = "$good" ]; then
  log "already at known-good ${good:0:7}; the problem is not the code (check media/audio: journalctl -u radio)"
  exit 0
fi

log "rolling back ${current:0:7} -> known-good ${good:0:7}"
git_as_user checkout --detach --force --quiet "$good"
systemctl reset-failed radio.service
systemctl start radio.service
