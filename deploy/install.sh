#!/usr/bin/env bash
# One-time install on the Pi. Run as your normal user from the repo clone:
#   deploy/install.sh
# Installs packages, the poweroff permission, the systemd units and the
# rollback helper. It does not edit config.txt or ALSA settings (the guide
# does those by hand) and does not start the radio.
set -euo pipefail

main() {
  local repo user tmp
  repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  user="$(id -un)"
  [ "$(id -u)" -ne 0 ] || { echo "Run as your normal user, not with sudo."; exit 1; }
  cd "$repo"

  echo "== Packages"
  sudo apt-get update
  sudo apt-get install -y python3-pygame python3-gpiozero python3-lgpio alsa-utils git

  echo "== Groups (audio, gpio) for $user"
  sudo usermod -aG audio,gpio "$user"

  echo "== Poweroff permission for the 8-second hold"
  tmp="$(mktemp)"
  echo "$user ALL=(root) NOPASSWD: /usr/bin/systemctl poweroff" > "$tmp"
  sudo visudo -cf "$tmp"
  sudo install -m 0440 -o root -g root "$tmp" /etc/sudoers.d/radio-poweroff
  rm -f "$tmp"

  echo "== Rollback helper and systemd units"
  sudo install -m 0755 deploy/rollback.sh /usr/local/bin/radio-rollback
  for unit in radio.service radio-rollback.service; do
    sed -e "s|@USER@|$user|g" -e "s|@REPO@|$repo|g" "deploy/$unit" \
      | sudo tee "/etc/systemd/system/$unit" >/dev/null
  done
  if [ ! -f /etc/default/radio ]; then
    sudo install -m 0644 deploy/radio.default /etc/default/radio
  fi
  sudo systemctl daemon-reload

  echo "== Marking this commit known-good"
  git tag -f known-good HEAD >/dev/null

  echo "== Done. Next: python3 -m radio --check, then sudo systemctl enable --now radio"
}

main "$@"
