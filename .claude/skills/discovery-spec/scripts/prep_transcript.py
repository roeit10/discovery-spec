#!/usr/bin/env python3
"""Timeless-style transcript ("שם (278.03): טקסט") -> same lines with [04:38] instead of seconds.

The minute marks in the internal check come from here, not from mental arithmetic.
Other formats (already mm:ss, or no timestamps) pass through unchanged.

Usage: python3 prep_transcript.py <transcript.txt> > transcript.mmss.txt
"""
import re, sys
from pathlib import Path

LINE = re.compile(r"^(?P<who>[^()\n]{1,40}?)\s*\((?P<sec>\d+(?:\.\d+)?)\)\s*:\s*(?P<text>.*)$")
text = Path(sys.argv[1]).read_text(encoding="utf-8")
n = 0
for ln in text.splitlines():
    m = LINE.match(ln.strip())
    if m:
        s = int(float(m["sec"]))
        print(f"[{s // 60:02d}:{s % 60:02d}] {m['who'].strip()}: {m['text']}")
        n += 1
    else:
        print(ln)
print(f"# {n} שורות עם זמן הומרו לדקות:שניות", file=sys.stderr)
