#!/usr/bin/env bash
# Run on the Mac. Converts a source media tree into the radio's format:
#   * idents and the welcome clip become 44.1 kHz stereo WAV
#   * every other recording becomes 44.1 kHz stereo MP3
#   * everything is loudness-normalised so voice and music play at similar levels
#   * other files (stations.json, memory.txt, photos/) are copied unchanged
#
# Voice-overs: put a message next to a song with ".voice" before the extension,
#   02-our-song.mp3
#   02-our-song.voice.m4a
# and the two are mixed into one track: the song starts quietly, the message
# plays over it, then the song fades up to full volume.
#
#   brew install ffmpeg
#   tools/prepare_media.sh ~/Desktop/radio-source ~/Desktop/radio-media
#
# Voice-over tuning (optional environment variables):
#   VOICE_DELAY=0.5   seconds of song before the message starts
#   DUCK_LEVEL=0.25   song volume while the message plays (1 = full)
#   DUCK_FADE=2       seconds for the song to fade back up afterwards
#   VOICE_GAIN=1      message volume (1.3 = a bit louder)
set -euo pipefail

src="${1:?usage: prepare_media.sh SOURCE_DIR OUTPUT_DIR}"
out="${2:?usage: prepare_media.sh SOURCE_DIR OUTPUT_DIR}"
command -v ffmpeg >/dev/null || { echo "ffmpeg not found: brew install ffmpeg"; exit 1; }
command -v ffprobe >/dev/null || { echo "ffprobe not found: brew install ffmpeg"; exit 1; }
[ -f "$src/stations.json" ] || { echo "$src/stations.json not found"; exit 1; }

VOICE_DELAY="${VOICE_DELAY:-0.5}"
DUCK_LEVEL="${DUCK_LEVEL:-0.25}"
DUCK_FADE="${DUCK_FADE:-2}"
VOICE_GAIN="${VOICE_GAIN:-1}"

src="$(cd "$src" && pwd)"
mkdir -p "$out"
out="$(cd "$out" && pwd)"

NORM="loudnorm=I=-16:TP=-1.5:LRA=11"

lower() { printf '%s' "$1" | tr '[:upper:]' '[:lower:]'; }

is_audio() {
  case "$(lower "${1##*.}")" in
    ogg|mp3|wav|m4a|aac|aiff|aif|flac) return 0 ;;
  esac
  return 1
}

is_voice() {  # NAME.voice.EXT
  case "$(lower "$(basename "$1")")" in *.voice.*) return 0 ;; esac
  return 1
}

voice_for() {  # print the NAME.voice.* file for song NAME.EXT, if any
  local stem="${1%.*}" candidate
  for candidate in "$stem".voice.* "$stem".Voice.* "$stem".VOICE.*; do
    if [ -f "$candidate" ] && is_audio "$candidate"; then
      printf '%s' "$candidate"
      return 0
    fi
  done
  return 1
}

song_for() {  # print the song NAME.EXT for voice file NAME.voice.EXT, if any
  local stem candidate
  stem="$(printf '%s' "${1%.*}" | sed -E 's/\.[Vv][Oo][Ii][Cc][Ee]$//')"
  for candidate in "$stem".*; do
    if [ -f "$candidate" ] && is_audio "$candidate" && ! is_voice "$candidate"; then
      printf '%s' "$candidate"
      return 0
    fi
  done
  return 1
}

encode() {  # encode <dest> <ffmpeg args before output...>
  local dest="$1"
  shift
  case "$dest" in
    *.wav) ffmpeg -nostdin -loglevel error -y "$@" -vn -ac 2 -ar 44100 -c:a pcm_s16le "$dest" ;;
    *) ffmpeg -nostdin -loglevel error -y "$@" -vn -ac 2 -ar 44100 -c:a libmp3lame -q:a 2 "$dest" ;;
  esac
}

converted=0
mixed=0
copied=0
warnings=0
while IFS= read -r -d '' file; do
  rel="${file#"$src"/}"
  name="$(basename "$rel")"
  case "$name" in .*) continue ;; esac

  if ! is_audio "$file"; then
    mkdir -p "$out/$(dirname "$rel")"
    cp "$file" "$out/$rel"
    copied=$((copied + 1))
    continue
  fi

  if is_voice "$file"; then
    # Mixed in when its song is processed.
    if ! song_for "$file" >/dev/null; then
      echo "WARN   $rel has no matching song (expected ${name%.voice.*}.mp3/.m4a/...), skipped"
      warnings=$((warnings + 1))
    fi
    continue
  fi

  stem="${rel%.*}"
  case "$(lower "$(basename "$stem")")" in
    ident|welcome)
      # Lower-case name: the Pi's filesystem is case-sensitive.
      dest="$out/$(dirname "$rel")/$(lower "$(basename "$stem")").wav"
      ;;
    *) dest="$out/$stem.mp3" ;;
  esac
  mkdir -p "$(dirname "$dest")"

  voice="$(voice_for "$file" || true)"
  if [ -z "$voice" ]; then
    encode "$dest" -i "$file" -af "$NORM"
    echo "audio  $rel -> ${dest#"$out"/}"
    converted=$((converted + 1))
    continue
  fi

  length="$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$voice")"
  delay_ms="$(awk -v d="$VOICE_DELAY" 'BEGIN { printf "%d", d * 1000 }')"
  fade_at="$(awk -v d="$VOICE_DELAY" -v l="$length" 'BEGIN { printf "%.3f", d + l }')"
  duck="if(lt(t,$fade_at),$DUCK_LEVEL,if(lt(t,$fade_at+$DUCK_FADE),$DUCK_LEVEL+(1-$DUCK_LEVEL)*(t-$fade_at)/$DUCK_FADE,1))"
  graph="[0:a]aformat=channel_layouts=stereo,$NORM,aresample=44100,volume='$duck':eval=frame[song];"
  graph+="[1:a]aformat=channel_layouts=stereo,$NORM,aresample=44100,volume=$VOICE_GAIN,adelay=$delay_ms:all=1[voice];"
  graph+="[song][voice]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.84:level=false"
  encode "$dest" -i "$file" -i "$voice" -filter_complex "$graph"
  echo "mixed  $rel + $(basename "$voice") -> ${dest#"$out"/}  (song back up at ${fade_at}s)"
  mixed=$((mixed + 1))
done < <(find "$src" -type f -print0 | sort -z)

echo "Done: $converted converted, $mixed mixed with voice-overs, $copied other file(s) copied, $warnings warning(s) -> $out"
