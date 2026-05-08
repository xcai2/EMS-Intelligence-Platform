#!/usr/bin/env bash
# EMS Intelligence Platform — FFmpeg assembly
# Run AFTER generate_voice.py and record_demo.js have both completed.
# Usage: bash assemble.sh

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="$SCRIPT_DIR/output"

WEBM="$OUT/screen_recording.webm"
MP4="$OUT/screen_recording.mp4"
VOICE="$OUT/voiceover.mp3"
MERGED="$OUT/merged.mp4"
SUBS="$OUT/subtitles.srt"
FINAL="$OUT/final_output.mp4"

echo "Checking required files…"
for f in "$WEBM" "$VOICE" "$SUBS"; do
  [ -f "$f" ] || { echo "ERROR: Missing $f"; exit 1; }
done

# Step 1 — webm → mp4 (lossless repack)
echo "Step 1/3  webm → mp4…"
ffmpeg -y -i "$WEBM" \
  -c:v libx264 -preset slow -crf 18 \
  -pix_fmt yuv420p \
  "$MP4"

# Step 2 — replace audio with voiceover
echo "Step 2/3  merge voiceover…"
ffmpeg -y \
  -i "$MP4" \
  -i "$VOICE" \
  -c:v copy \
  -c:a aac -b:a 192k \
  -map 0:v:0 -map 1:a:0 \
  -shortest \
  "$MERGED"

# Step 3 — finalize (subtitle burning requires libass; skip and use .srt as external track)
echo "Step 3/3  finalizing…"
cd "$OUT"
cp merged.mp4 final_output.mp4

echo ""
echo "✅  final_output.mp4 is ready: $FINAL"
echo "    $(du -sh "$FINAL" | cut -f1)   $(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$FINAL" 2>/dev/null | awk '{printf "%.0fs", $1}') total"
