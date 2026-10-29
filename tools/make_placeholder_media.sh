#!/usr/bin/env bash
# macOS only: regenerate the placeholder voice clips and tone tracks in media-example/.
# Real idents should be your own recordings; these just make the example playable.
set -euo pipefail

repo="$(cd "$(dirname "$0")/.." && pwd)"
media="$repo/media-example"

speak() {  # speak <output.wav> <text>
  mkdir -p "$(dirname "$1")"
  say --file-format=WAVE --data-format=LEI16@22050 -o "$1" "$2"
  echo "wrote $1"
}

speak "$media/home/welcome.wav" "Welcome to Five Years F M. Turn the dial to find a station."

python3 - "$media" <<'PY' | while IFS=$'\t' read -r folder text; do speak "$media/$folder/ident.wav" "$text"; done
import json, sys
for s in json.load(open(sys.argv[1] + "/stations.json"))["stations"]:
    print(f'{s["folder"]}\tYou are listening to {s["freq"]}, {s["name"]}.')
PY

python3 "$repo/tools/make_sounds.py" --tones "$media"
