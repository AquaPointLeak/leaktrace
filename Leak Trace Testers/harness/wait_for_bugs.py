#!/usr/bin/env python3
"""Coordinator helper: block until there is work to do.

Returns (prints a one-line reason) when any of these is true:
  - a bug is in status 'reported' or 'reopened' (new work)
  - every tester agent reports state 'done'
  - --max seconds have passed (default 540)
Polls every 15 s. Usage: python3 harness/wait_for_bugs.py [--max 540]
"""
import json, sys, time
from pathlib import Path

BOARD = Path(__file__).resolve().parent.parent / 'board'
TESTERS = ['tester-a', 'tester-b']

def check():
    new = []
    for p in sorted((BOARD / 'bugs').glob('BUG-*.json')):
        try:
            d = json.loads(p.read_text())
        except Exception:
            continue
        if d.get('status') in ('reported', 'reopened'):
            new.append(d['id'])
    states = {}
    for t in TESTERS:
        p = BOARD / 'agents' / (t + '.json')
        try:
            states[t] = json.loads(p.read_text()).get('state')
        except Exception:
            states[t] = 'not-started'
    return new, states

def main():
    mx = 540
    if '--max' in sys.argv:
        mx = int(sys.argv[sys.argv.index('--max') + 1])
    end = time.time() + mx
    while True:
        new, states = check()
        if new:
            print('NEW_BUGS', ' '.join(new), '| testers:', states); return
        if all(s == 'done' for s in states.values()):
            print('TESTERS_DONE | testers:', states); return
        if time.time() > end:
            print('TIMEOUT no new bugs | testers:', states); return
        time.sleep(15)

if __name__ == '__main__':
    main()
