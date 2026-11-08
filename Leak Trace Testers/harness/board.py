#!/usr/bin/env python3
"""Shared QA board CLI. Agents use this instead of editing board JSON by hand.

  Agent status (each agent writes only its own file):
    board.py init   <agent> --name N --model M --effort E --role R --tasks "a|b|c"
    board.py status <agent> [--state working|blocked|waiting|done] [--step TEXT] [--log TEXT]
                            [--done N ...] [--undone N ...]          (task numbers are 1-based)

  Bugs:
    board.py bug new --reporter A --title T --page P --viewport desktop|mobile|both
                     --severity critical|high|medium|low --steps S --expected E --actual A --fix F
                     [--area auth|reports|presets|pdf|catalogue|portal|nav|ui|other]
                     -> prints the new id (BUG-001, ...)
    board.py bug update BUG-001 [--status S] [--set key=value ...] [--note TEXT --by AGENT]
    board.py bug show BUG-001
    board.py bug list [--status S]

  Mock mailbox (confirmation / magic / reset links):
    board.py mail <email>
"""
import argparse, fcntl, json, os, sys, time, urllib.request, urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BOARD = ROOT / 'board'
AGENTS = BOARD / 'agents'
BUGS = BOARD / 'bugs'
STATUSES = ['reported', 'triaged', 'duplicate', 'rejected', 'fix-proposed', 'awaiting-approval',
            'approved', 'declined', 'fixed', 'verified', 'reopened']

def ts():
    return time.strftime('%H:%M:%S')

def atomic_write(p, data):
    tmp = p.with_name('.' + p.name + '.tmp')
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(p)

class Locked:
    def __init__(self, p): self.lock = p.with_name('.' + p.name + '.lock')
    def __enter__(self):
        self.f = open(self.lock, 'w'); fcntl.flock(self.f, fcntl.LOCK_EX); return self
    def __exit__(self, *a):
        fcntl.flock(self.f, fcntl.LOCK_UN); self.f.close()

def cmd_init(a):
    AGENTS.mkdir(parents=True, exist_ok=True)
    tasks = [t.strip() for t in a.tasks.split('|') if t.strip()]
    data = {'id': a.agent, 'name': a.name, 'model': a.model, 'effort': a.effort, 'role': a.role,
            'state': 'working', 'step': 'Starting up', 'started': time.time(), 'updated': time.time(),
            'tasks': [{'text': t, 'done': False} for t in tasks], 'log': [ts() + '  started']}
    atomic_write(AGENTS / (a.agent + '.json'), data)
    print('ok')

def cmd_status(a):
    p = AGENTS / (a.agent + '.json')
    with Locked(p):
        d = json.loads(p.read_text())
        if a.state: d['state'] = a.state
        if a.step: d['step'] = a.step
        for n in a.done or []:
            if 1 <= n <= len(d['tasks']): d['tasks'][n - 1]['done'] = True
        for n in a.undone or []:
            if 1 <= n <= len(d['tasks']): d['tasks'][n - 1]['done'] = False
        if a.log: d['log'] = (d['log'] + [ts() + '  ' + a.log])[-30:]
        elif a.step: d['log'] = (d['log'] + [ts() + '  ' + a.step])[-30:]
        d['updated'] = time.time()
        atomic_write(p, d)
    print('ok')

def cmd_bug_new(a):
    BUGS.mkdir(parents=True, exist_ok=True)
    n = 1
    while True:
        bid = 'BUG-%03d' % n
        p = BUGS / (bid + '.json')
        try:
            fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            n += 1; continue
        data = {'id': bid, 'reporter': a.reporter, 'title': a.title, 'page': a.page, 'viewport': a.viewport,
                'severity': a.severity, 'area': a.area, 'steps': a.steps, 'expected': a.expected,
                'actual': a.actual, 'requested_fix': a.fix, 'status': 'reported',
                'created': time.time(), 'updated': time.time(),
                'history': [{'at': ts(), 'by': a.reporter, 'text': 'reported'}]}
        with os.fdopen(fd, 'w') as f:
            json.dump(data, f, indent=2)
        print(bid)
        return

def cmd_bug_update(a):
    p = BUGS / (a.id + '.json')
    if not p.exists(): sys.exit('no such bug ' + a.id)
    with Locked(p):
        d = json.loads(p.read_text())
        if a.status:
            if a.status not in STATUSES: sys.exit('status must be one of ' + ', '.join(STATUSES))
            d['status'] = a.status
            d['history'].append({'at': ts(), 'by': a.by or '?', 'text': 'status -> ' + a.status})
        for kv in a.set or []:
            k, _, v = kv.partition('=')
            try: v = json.loads(v)
            except Exception: pass
            d[k] = v
        if a.note: d['history'].append({'at': ts(), 'by': a.by or '?', 'text': a.note})
        d['updated'] = time.time()
        atomic_write(p, d)
    print('ok')

def cmd_bug_show(a):
    print((BUGS / (a.id + '.json')).read_text())

def cmd_bug_list(a):
    for p in sorted(BUGS.glob('BUG-*.json')):
        d = json.loads(p.read_text())
        if a.status and d['status'] != a.status: continue
        print('%s  %-17s %-8s %-7s %s' % (d['id'], d['status'], d['severity'], d['viewport'], d['title']))

def cmd_mail(a):
    url = 'http://localhost:8787/mock/mailbox?to=' + urllib.parse.quote(a.email.lower())
    for m in json.loads(urllib.request.urlopen(url).read()):
        print('#%d  %s  %s\n    %s' % (m['id'], m['at'], m['kind'], m['link']))

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest='cmd', required=True)
    p = sp.add_parser('init'); p.add_argument('agent'); p.add_argument('--name', required=True)
    p.add_argument('--model', required=True); p.add_argument('--effort', required=True)
    p.add_argument('--role', required=True); p.add_argument('--tasks', required=True); p.set_defaults(f=cmd_init)
    p = sp.add_parser('status'); p.add_argument('agent'); p.add_argument('--state'); p.add_argument('--step')
    p.add_argument('--log'); p.add_argument('--done', type=int, nargs='*'); p.add_argument('--undone', type=int, nargs='*')
    p.set_defaults(f=cmd_status)
    b = sp.add_parser('bug').add_subparsers(dest='bcmd', required=True)
    p = b.add_parser('new')
    for k in ('reporter', 'title', 'page', 'steps', 'expected', 'actual', 'fix'):
        p.add_argument('--' + k, required=True)
    p.add_argument('--viewport', choices=['desktop', 'mobile', 'both'], required=True)
    p.add_argument('--severity', choices=['critical', 'high', 'medium', 'low'], required=True)
    p.add_argument('--area', default='other'); p.set_defaults(f=cmd_bug_new)
    p = b.add_parser('update'); p.add_argument('id'); p.add_argument('--status'); p.add_argument('--set', nargs='*')
    p.add_argument('--note'); p.add_argument('--by'); p.set_defaults(f=cmd_bug_update)
    p = b.add_parser('show'); p.add_argument('id'); p.set_defaults(f=cmd_bug_show)
    p = b.add_parser('list'); p.add_argument('--status'); p.set_defaults(f=cmd_bug_list)
    p = sp.add_parser('mail'); p.add_argument('email'); p.set_defaults(f=cmd_mail)
    a = ap.parse_args(); a.f(a)

if __name__ == '__main__':
    main()
