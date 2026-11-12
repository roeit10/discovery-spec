#!/bin/bash
# spec.html -> spec.pdf through Chrome headless (Hebrew, fonts, A4, page numbers).
# Usage: render_pdf.sh <spec.html> [spec.pdf]
set -e
IN="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"; OUT="${2:-${1%.html}.pdf}"
for c in "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" "$(command -v google-chrome || true)" "$(command -v google-chrome-stable || true)" "$(command -v chromium || true)" "/mnt/c/Program Files/Google/Chrome/Application/chrome.exe" "/c/Program Files/Google/Chrome/Application/chrome.exe"; do
  [ -n "$c" ] && [ -x "$c" ] && CHROME="$c" && break
done
[ -z "$CHROME" ] && { echo "Chrome לא נמצא. להתקין Google Chrome ולהריץ שוב. בינתיים יש spec.html שאפשר לפתוח בדפדפן."; exit 1; }
"$CHROME" --headless --disable-gpu --no-pdf-header-footer --hide-scrollbars --virtual-time-budget=10000 --print-to-pdf="$OUT" "file://$IN" 2>/dev/null
PAGES=$( (command -v pdfinfo >/dev/null && pdfinfo "$OUT" | awk '/^Pages:/{print $2}') || echo "?")
echo "OK $OUT ($(du -k "$OUT" | cut -f1)KB, $PAGES עמודים)"
