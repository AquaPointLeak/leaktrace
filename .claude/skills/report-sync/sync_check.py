#!/usr/bin/env python3
"""Compare leak-report-builder-desktop.html and leak-report-builder-mobile.html.

Splits each file into named chunks (one per top-level JS function/const, plus the
<style> block and the page markup) and compares them chunk by chunk. Differences
that are intentional (the desktop sidebar vs the mobile topbar/list layout) are
recorded in baseline.json, so only NEW drift is reported.

Usage:
  sync_check.py                 report new / resolved differences (exit 1 if any new)
  sync_check.py --all           also list the known, accepted differences
  sync_check.py --show NAME     print the diff for one chunk (e.g. renderEditor, <style>)
  sync_check.py --accept        record the current differences as the new baseline
"""
import difflib
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DESKTOP = ROOT / "leak-report-builder-desktop.html"
MOBILE = ROOT / "leak-report-builder-mobile.html"
BASELINE = HERE / "baseline.json"

DECL = re.compile(r"^(?:async\s+)?function\s+([A-Za-z0-9_$]+)|^(?:const|let|var)\s+([A-Za-z0-9_$]+)")


def chunks(path):
    lines = path.read_text(encoding="utf-8").splitlines()
    # The app script is the last inline <script> (the earlier ones are CDN tags).
    start = max(i for i, l in enumerate(lines) if l.strip() == "<script>")
    end = next(i for i in range(start, len(lines)) if lines[i].strip() == "</script>")
    style_start = next(i for i, l in enumerate(lines) if l.strip().startswith("<style"))
    style_end = next(i for i, l in enumerate(lines) if l.strip() == "</style>")

    out = {
        "<head>": (lines[:style_start], 1),
        "<style>": (lines[style_start:style_end + 1], style_start + 1),
        "<markup>": (lines[style_end + 1:start] + lines[end:], style_end + 2),
    }
    name, buf, buf_line = "<script-preamble>", [], start + 1
    for i in range(start, end + 1):
        m = DECL.match(lines[i])
        if m:
            add_chunk(out, name, buf, buf_line)
            name, buf, buf_line = m.group(1) or m.group(2), [], i + 1
        buf.append(lines[i])
    add_chunk(out, name, buf, buf_line)
    return out


def add_chunk(out, name, buf, line):
    key, n = name, 2
    while key in out:  # duplicate declarations get #2, #3...
        key, n = f"{name}#{n}", n + 1
    out[key] = (buf, line)


def norm(lines):
    # Ignore trailing whitespace and blank lines so formatting noise isn't drift.
    return [l.rstrip() for l in lines if l.strip()]


def diff_lines(a, b):
    return [l for l in difflib.unified_diff(norm(a), norm(b), lineterm="", n=0)
            if not l.startswith(("---", "+++", "@@"))]


def signature(d, m):
    if d is None:
        kind, body = "only-mobile", norm(m)
    elif m is None:
        kind, body = "only-desktop", norm(d)
    else:
        body = diff_lines(d, m)
        if not body:
            return None
        kind = "differs"
    return kind + ":" + hashlib.sha1("\n".join(body).encode()).hexdigest()[:12]


def main(argv):
    dc, mc = chunks(DESKTOP), chunks(MOBILE)
    names = list(dict.fromkeys(list(dc) + list(mc)))

    if "--show" in argv:
        target = argv[argv.index("--show") + 1]
        d, m = dc.get(target), mc.get(target)
        if not d and not m:
            sys.exit(f"No chunk named {target!r}")
        print(f"desktop line {d[1] if d else '-'}  |  mobile line {m[1] if m else '-'}")
        for l in difflib.unified_diff(norm(d[0]) if d else [], norm(m[0]) if m else [],
                                      "desktop", "mobile", lineterm="", n=2):
            print(l)
        return 0

    current = {}
    for n in names:
        sig = signature(dc[n][0] if n in dc else None, mc[n][0] if n in mc else None)
        if sig:
            current[n] = sig

    if "--accept" in argv:
        BASELINE.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n")
        print(f"Baseline updated: {len(current)} accepted differences.")
        return 0

    baseline = json.loads(BASELINE.read_text()) if BASELINE.exists() else {}

    def where(n):
        parts = [f"desktop:{dc[n][1]}" if n in dc else "desktop:-",
                 f"mobile:{mc[n][1]}" if n in mc else "mobile:-"]
        return "  (" + ", ".join(parts) + ")"

    new = [n for n in current if baseline.get(n) != current[n]]
    resolved = [n for n in baseline if n not in current]
    known = [n for n in current if baseline.get(n) == current[n]]

    if new:
        print("NEW DIFFERENCES (not in baseline - likely drift):")
        for n in new:
            note = " [was a known difference, but it changed]" if n in baseline else ""
            print(f"  {current[n].split(':')[0]:13} {n}{where(n)}{note}")
    if resolved:
        print("NOW IDENTICAL (were known differences):")
        for n in resolved:
            print(f"  {n}")
    if "--all" in argv and known:
        print("KNOWN LAYOUT DIFFERENCES (accepted):")
        for n in known:
            print(f"  {current[n].split(':')[0]:13} {n}{where(n)}")
    if not new and not resolved:
        print(f"In sync. {len(known)} known layout differences, nothing new.")
    return 1 if new else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
