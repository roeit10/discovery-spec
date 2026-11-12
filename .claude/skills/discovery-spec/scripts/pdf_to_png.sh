#!/bin/bash
# Turn each PDF page into a PNG so Claude can look at the pages before delivering.
# Usage: pdf_to_png.sh <spec.pdf> [out_dir]   -> <out_dir>/page-1.png, page-2.png ...
set -e
PDF="$1"; OUT="${2:-$(dirname "$1")/.pages}"; mkdir -p "$OUT"
if command -v pdftoppm >/dev/null; then
  pdftoppm -r 70 -png "$PDF" "$OUT/page"
  ls "$OUT"/page-*.png
else
  echo "pdftoppm לא מותקן - לפתוח את ה-PDF ישירות בכלי Read (pages: \"1-3\") ולבדוק כל עמוד."
fi
