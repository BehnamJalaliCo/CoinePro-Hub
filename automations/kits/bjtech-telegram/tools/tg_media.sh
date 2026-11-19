#!/usr/bin/env bash
# Telegram-sized media (ffmpeg):
#   bash KIT/tools/tg_media.sh voice <in.wav|ogg|mp3> <out.ogg>   OGG/Opus mono 48 kHz 64k (a voice note)
#   bash KIT/tools/tg_media.sh clip  <in.mp4> <out.mp4>           H.264 High + AAC, faststart, <= 48 MB
# The voice's zero-tolerance QC (audio_qc 0/0/0) runs on the take AND on <out.ogg> (REELS/README.md, Voice).
set -euo pipefail
what="${1:-}"; in="${2:-}"; out="${3:-}"
[[ -f "$in" && -n "$out" ]] || { echo "usage: tg_media.sh voice|clip <in> <out>" >&2; exit 2; }
case "$what" in
  voice)
    ffmpeg -nostdin -loglevel error -y -i "$in" -vn -ac 1 -ar 48000 -c:a libopus -b:a 64k -application voip "$out"
    dur="$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$out")"
    echo "ok $out ${dur%.*} s $(stat -c %s "$out") bytes" ;;
  clip)
    dur="$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$in")"
    kbps=$(python3 -c "print(min(6000, int(48*1024*1024*8*0.92/float('$dur')/1000) - 160))")
    ffmpeg -nostdin -loglevel error -y -i "$in" -map 0:v:0 -map 0:a:0? -c:v libx264 -preset slow -profile:v high \
      -pix_fmt yuv420p -b:v "${kbps}k" -maxrate "$((kbps * 11 / 10))k" -bufsize "$((kbps * 2))k" \
      -c:a aac -b:a 128k -movflags +faststart "$out"
    size=$(stat -c %s "$out")
    (( size <= 48 * 1024 * 1024 )) || { echo "over 48 MB ($size)" >&2; exit 1; }
    echo "ok $out ${dur%.*} s $size bytes" ;;
  *) echo "usage: tg_media.sh voice|clip <in> <out>" >&2; exit 2 ;;
esac
