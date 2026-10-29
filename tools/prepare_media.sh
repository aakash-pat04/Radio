#!/usr/bin/env bash
# Run on the Mac. Converts a source media tree into the radio's format:
# every audio file becomes 44.1 kHz stereo OGG Vorbis, loudness-normalised so
# voice recordings and music play at similar levels. Everything else
# (stations.json, memory.txt, photos/) is copied unchanged.
#
#   brew install ffmpeg
#   tools/prepare_media.sh ~/Desktop/radio-source ~/Desktop/radio-media
set -euo pipefail

src="${1:?usage: prepare_media.sh SOURCE_DIR OUTPUT_DIR}"
out="${2:?usage: prepare_media.sh SOURCE_DIR OUTPUT_DIR}"
command -v ffmpeg >/dev/null || { echo "ffmpeg not found: brew install ffmpeg"; exit 1; }
[ -f "$src/stations.json" ] || { echo "$src/stations.json not found"; exit 1; }

src="$(cd "$src" && pwd)"
mkdir -p "$out"
out="$(cd "$out" && pwd)"

converted=0
copied=0
while IFS= read -r -d '' file; do
  rel="${file#"$src"/}"
  case "$(basename "$rel")" in .*) continue ;; esac
  ext="$(printf '%s' "${rel##*.}" | tr '[:upper:]' '[:lower:]')"
  case "$ext" in
    ogg|mp3|wav|m4a|aac|aiff|aif|flac)
      dest="$out/${rel%.*}.ogg"
      mkdir -p "$(dirname "$dest")"
      ffmpeg -nostdin -loglevel error -y -i "$file" -vn -ac 2 -ar 44100 \
        -af loudnorm=I=-16:TP=-1.5:LRA=11 -c:a libvorbis -q:a 5 "$dest"
      echo "audio  $rel -> ${dest#"$out"/}"
      converted=$((converted + 1))
      ;;
    *)
      mkdir -p "$out/$(dirname "$rel")"
      cp "$file" "$out/$rel"
      copied=$((copied + 1))
      ;;
  esac
done < <(find "$src" -type f -print0)

echo "Done: $converted audio file(s) converted, $copied other file(s) copied into $out"
