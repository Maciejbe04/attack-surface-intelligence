#!/usr/bin/env bash
# Reset demo data, record the walkthrough with captions, convert to MP4.
# Needs: running SurfaceX stack (+ --profile defectdojo), Google Chrome, Node, and Playwright in $PW_DIR.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
PW_DIR="${PW_DIR:?set PW_DIR to a folder with node_modules/playwright}"
OUT="${OUT:-$REPO/demo/out}"
rm -rf "$OUT/raw" "$OUT/shots"; mkdir -p "$OUT"
"$REPO/demo/record/reset.sh"
cp "$REPO/demo/record/demo.mjs" "$PW_DIR/demo.mjs"
VIDEO=$(cd "$PW_DIR" && REPO="$REPO" OUT="$OUT" node demo.mjs | sed -n 's/^VIDEO //p')
ffmpeg -y -loglevel error -i "$VIDEO" -c:v libx264 -preset slow -crf 23 -pix_fmt yuv420p -movflags +faststart "$OUT/SurfaceX-demo.mp4"
echo "MP4: $OUT/SurfaceX-demo.mp4"

# Slides: refresh screenshots (JPEG, small PDF) and render the deck.
mkdir -p "$REPO/demo/pitch/img"
for f in "$OUT"/shots/*.png; do
  n=$(basename "$f" .png | sed 's/^[0-9]*-//')
  sips -s format jpeg -s formatOptions 80 "$f" --out "$REPO/demo/pitch/img/$n.jpg" >/dev/null
done
cp "$REPO/demo/pitch/build.mjs" "$PW_DIR/build.mjs"
(cd "$PW_DIR" && PITCH_DIR="$REPO/demo/pitch" OUT_PDF="$OUT/SurfaceX-HackNation2026.pdf" TEAM="${TEAM:-}" VIDEO_URL="${VIDEO_URL:-}" node build.mjs)
