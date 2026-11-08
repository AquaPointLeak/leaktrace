#!/usr/bin/env python3
"""Copy the LeakTrace pages into ../site with Supabase swapped for the local mock.

The originals in the LeakTrace folder are never modified. Re-run after any fix
so the testers pick up the new code:   python3 harness/build_site.py
"""
import re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent      # Leak Trace Testers
APP = ROOT.parent                                    # LeakTrace (originals)
SITE = ROOT / 'site'
PAGES = ['index.html', 'aquapoint-portal.html',
         'leak-report-builder-desktop.html', 'leak-report-builder-mobile.html']

CDN = re.compile(r'<script src="https://cdn\.jsdelivr\.net/npm/@supabase/supabase-js@[0-9.]+"[^>]*></script>')
URL = re.compile(r"(const SUPABASE_URL\s*=\s*)'https://[a-z0-9]+\.supabase\.co'")
BANNER = ('<div id="qa-banner" style="position:fixed;bottom:0;right:0;z-index:99999;'
          'background:#1f6f5c;color:#fff;font:600 10px/1 system-ui;padding:3px 6px;'
          'border-top-left-radius:6px;opacity:.75;pointer-events:none;">QA MOCK</div>')

def main():
    SITE.mkdir(exist_ok=True)
    for name in PAGES:
        src = (APP / name).read_text(encoding='utf-8')
        out, n1 = CDN.subn('<script src="/harness/mock-supabase.js"></script>', src)
        out, n2 = URL.subn(r"\1'http://localhost:8787/mock'", out)
        if n1 != 1 or n2 != 1:
            sys.exit('%s: expected 1 supabase script and 1 SUPABASE_URL, found %d and %d' % (name, n1, n2))
        if 'supabase.co' in out:
            sys.exit('%s: a supabase.co reference survived the rewrite' % name)
        out = out.replace('</body>', BANNER + '</body>', 1)
        (SITE / name).write_text(out, encoding='utf-8')
        print('built site/%s' % name)

if __name__ == '__main__':
    main()
