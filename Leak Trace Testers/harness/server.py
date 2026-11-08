#!/usr/bin/env python3
"""LeakTrace QA harness server (stdlib only).

Serves:
  /site/...        copies of the app pages with Supabase swapped for the mock
  /harness/...     mock client, dashboard
  /mock/...        the stand-in Supabase backend (auth, tables, rpc, storage)
  /api/state       everything the dashboard shows (agents, bugs, mailbox, db counts)

Data lives in ../mockdb (reset with:  python3 harness/server.py --reset).
Nothing here talks to the real Supabase project.
"""
import json, os, sys, threading, time, uuid, secrets, hashlib, mimetypes, shutil, urllib.parse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # .../Leak Trace Testers
HARNESS = ROOT / 'harness'
SITE = ROOT / 'site'
BOARD = ROOT / 'board'
MOCKDB = ROOT / 'mockdb'
MEDIA = MOCKDB / 'media'
DB_FILE = MOCKDB / 'db.json'
PORT = int(os.environ.get('PORT', '8787'))
CONFIRM_EMAIL = os.environ.get('CONFIRM_EMAIL', '1') == '1'   # real Supabase default is on

LOCK = threading.RLock()

def now_iso():
    return time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime()) + '.%03dZ' % (int(time.time() * 1000) % 1000)

def empty_db():
    return {'users': {}, 'tokens': {}, 'mailbox': [], 'counters': {},
            'tables': {'reports': [], 'presets': [], 'business_profile': [], 'public_presets': []},
            'media_tokens': {}, 'requests': 0}

def load_db():
    if DB_FILE.exists():
        try:
            return json.loads(DB_FILE.read_text())
        except Exception:
            pass
    return empty_db()

DB = None

def save_db():
    tmp = DB_FILE.with_suffix('.tmp')
    tmp.write_text(json.dumps(DB))
    tmp.replace(DB_FILE)

def admin_emails():
    try:
        accts = json.loads((HARNESS / 'test-accounts.json').read_text())
        return {a['email'].lower() for a in accts.get('accounts', []) if a.get('admin')}
    except Exception:
        return set()

def hash_pw(pw, salt):
    return hashlib.sha256((salt + pw).encode()).hexdigest()

def err(message, code='400', status=400):
    return status, {'error': {'message': message, 'code': code}}

# ---------------------------------------------------------------- auth

def user_public(u):
    return {'id': u['id'], 'email': u['email'], 'aud': 'authenticated', 'role': 'authenticated',
            'email_confirmed_at': u.get('confirmed_at'), 'created_at': u['created_at'],
            'app_metadata': {'provider': 'email'}, 'user_metadata': {}}

def new_session(u):
    tok = secrets.token_urlsafe(24)
    DB['tokens'][tok] = u['id']
    return {'access_token': tok, 'refresh_token': secrets.token_urlsafe(16), 'token_type': 'bearer',
            'expires_in': 3600, 'expires_at': int(time.time()) + 3600, 'user': user_public(u)}

def find_user(email):
    email = (email or '').strip().lower()
    for u in DB['users'].values():
        if u['email'] == email:
            return u
    return None

def mail(to, kind, link, page=''):
    DB['mailbox'].append({'id': len(DB['mailbox']) + 1, 'to': to, 'kind': kind, 'link': link,
                          'at': now_iso(), 'page': page})

def link_for(redirect, u, typ):
    s = new_session(u)
    base = (redirect or '').split('#')[0] or 'http://localhost:%d/site/leak-report-builder-desktop.html' % PORT
    frag = urllib.parse.urlencode({'access_token': s['access_token'], 'refresh_token': s['refresh_token'],
                                   'expires_in': 3600, 'token_type': 'bearer', 'type': typ})
    return base + '#' + frag

def auth_op(op, body, uid):
    if op == 'signup':
        email = (body.get('email') or '').strip().lower()
        pw = body.get('password') or ''
        if not email or '@' not in email:
            return err('Unable to validate email address: invalid format', 'validation_failed', 400)
        if len(pw) < 6:
            return err('Password should be at least 6 characters.', 'weak_password', 422)
        existing = find_user(email)
        if existing and existing.get('confirmed_at'):
            return err('User already registered', 'user_already_exists', 422)
        if existing:      # unconfirmed re-signup: resend like Supabase does
            u = existing
        else:
            salt = secrets.token_hex(8)
            u = {'id': str(uuid.uuid4()), 'email': email, 'salt': salt, 'pw': hash_pw(pw, salt),
                 'created_at': now_iso(), 'confirmed_at': None if CONFIRM_EMAIL else now_iso()}
            DB['users'][u['id']] = u
        redirect = (body.get('options') or {}).get('emailRedirectTo')
        if CONFIRM_EMAIL:
            mail(email, 'Confirm your signup', link_for(redirect, u, 'signup'), redirect or '')
            return 200, {'data': {'user': user_public(u), 'session': None}}
        return 200, {'data': {'user': user_public(u), 'session': new_session(u)}}

    if op == 'password':
        u = find_user(body.get('email'))
        if not u or u['pw'] != hash_pw(body.get('password') or '', u['salt']):
            return err('Invalid login credentials', 'invalid_credentials', 400)
        if not u.get('confirmed_at'):
            return err('Email not confirmed', 'email_not_confirmed', 400)
        return 200, {'data': {'user': user_public(u), 'session': new_session(u)}}

    if op == 'recover':
        u = find_user(body.get('email'))
        if u:
            redirect = (body.get('options') or {}).get('redirectTo')
            mail(u['email'], 'Reset your password', link_for(redirect, u, 'recovery'), redirect or '')
        return 200, {'data': {}}

    if op == 'otp':
        email = (body.get('email') or '').strip().lower()
        if not email or '@' not in email:
            return err('Unable to validate email address: invalid format', 'validation_failed', 400)
        u = find_user(email)
        if not u:
            salt = secrets.token_hex(8)
            u = {'id': str(uuid.uuid4()), 'email': email, 'salt': salt, 'pw': hash_pw(secrets.token_hex(8), salt),
                 'created_at': now_iso(), 'confirmed_at': now_iso(), 'otp_only': True}
            DB['users'][u['id']] = u
        redirect = (body.get('options') or {}).get('emailRedirectTo')
        mail(email, 'Your magic link', link_for(redirect, u, 'magiclink'), redirect or '')
        return 200, {'data': {'user': None, 'session': None}}

    if op == 'session':          # exchange a token from a link for a full session
        tok = body.get('access_token')
        uid2 = DB['tokens'].get(tok)
        if not uid2:
            return err('Invalid or expired link', 'otp_expired', 401)
        u = DB['users'][uid2]
        if body.get('type') in ('signup', 'magiclink', 'recovery') and not u.get('confirmed_at'):
            u['confirmed_at'] = now_iso()
        return 200, {'data': {'session': {'access_token': tok, 'refresh_token': body.get('refresh_token', ''),
                                          'token_type': 'bearer', 'expires_in': 3600,
                                          'expires_at': int(time.time()) + 3600, 'user': user_public(u)}}}

    if op == 'user':
        if not uid:
            return err('Auth session missing!', 'session_not_found', 401)
        u = DB['users'][uid]
        if 'password' in body:
            if len(body['password'] or '') < 6:
                return err('Password should be at least 6 characters.', 'weak_password', 422)
            if u['pw'] == hash_pw(body['password'], u['salt']):
                return err('New password should be different from the old password.', 'same_password', 422)
            u['pw'] = hash_pw(body['password'], u['salt'])
        return 200, {'data': {'user': user_public(u)}}

    if op == 'logout':
        return 200, {'data': {}}

    return err('Unknown auth op ' + op, '404', 404)

# ---------------------------------------------------------------- tables (row-level rules approximate the real ones)

def user_email(uid):
    u = DB['users'].get(uid) if uid else None
    return u['email'] if u else None

def is_admin(uid):
    e = user_email(uid)
    return bool(e and e in admin_emails())

def can_read(table, row, uid):
    if not uid:
        return False
    if table == 'reports':
        if row.get('owner_id') == uid:
            return True
        e = user_email(uid)
        return bool(row.get('shared_with_client') and e and (row.get('client_email') or '').lower() == e)
    if table == 'presets':
        return row.get('owner_id') == uid
    if table == 'business_profile':
        if row.get('owner_id') == uid:
            return True
        return any(can_read('reports', r, uid) for r in DB['tables']['reports'] if r.get('owner_id') == row.get('owner_id'))
    if table == 'public_presets':
        return row.get('review_state') == 'approved' or row.get('owner_id') == uid or is_admin(uid)
    return False

def can_write(table, row, uid):
    if not uid:
        return False
    if table == 'public_presets' and is_admin(uid):
        return True
    return row.get('owner_id') == uid

def project(row, cols):
    if not cols or cols.strip() == '*':
        return dict(row)
    out = {}
    for c in cols.split(','):
        c = c.strip()
        if c:
            out[c] = row.get(c)
    return out

def matches(row, filters):
    for f in filters:
        if f['op'] == 'eq' and row.get(f['col']) != f['val']:
            return False
    return True

def rls_error(table):
    return err('new row violates row-level security policy for table "%s"' % table, '42501', 403)

def table_op(body, uid):
    table = body.get('table')
    if table not in DB['tables']:
        return err('relation "public.%s" does not exist' % table, '42P01', 404)
    rows = DB['tables'][table]
    op = body.get('op')
    filters = body.get('filters') or []
    returning = body.get('select')

    if op == 'select':
        res = [r for r in rows if matches(r, filters) and can_read(table, r, uid)]
        for col, asc in reversed(body.get('order') or []):
            res.sort(key=lambda r: (r.get(col) is None, r.get(col) or ''), reverse=not asc)
        if body.get('limit'):
            res = res[:int(body['limit'])]
        res = [project(r, body.get('columns')) for r in res]
        return 200, {'data': res}

    if op in ('upsert', 'insert'):
        vals = body.get('values')
        vals = vals if isinstance(vals, list) else [vals]
        key = body.get('onConflict') or ('owner_id' if table in ('presets', 'business_profile') else 'id')
        out = []
        for v in vals:
            v = dict(v)
            if not can_write(table, v, uid):
                return rls_error(table)
            existing = next((r for r in rows if key in v and r.get(key) == v.get(key)), None)
            if existing is not None and op == 'insert':
                return err('duplicate key value violates unique constraint "%s_pkey"' % table, '23505', 409)
            if existing is not None:
                if not can_write(table, existing, uid):
                    return rls_error(table)
                existing.update(v)
                existing['updated_at'] = now_iso()
                if table == 'public_presets' and not is_admin(uid):
                    existing['review_state'] = 'pending'      # edits go back through review
                    existing['review_note'] = None
                out.append(existing)
            else:
                v.setdefault('id', str(uuid.uuid4()))
                v['created_at'] = now_iso()
                v['updated_at'] = now_iso()
                if table == 'public_presets':
                    v.setdefault('copy_count', 0)
                    v['review_state'] = 'pending'
                    v.setdefault('review_note', None)
                rows.append(v)
                out.append(v)
        return 200, {'data': [project(r, returning) for r in out] if returning is not None else None}

    if op == 'update':
        vals = body.get('values') or {}
        out = []
        for r in rows:
            if matches(r, filters) and can_write(table, r, uid):
                r.update(vals)
                r['updated_at'] = now_iso()
                out.append(r)
        return 200, {'data': [project(r, returning) for r in out] if returning is not None else None}

    if op == 'delete':
        keep, gone = [], []
        for r in rows:
            (gone if matches(r, filters) and can_write(table, r, uid) else keep).append(r)
        DB['tables'][table] = keep
        return 200, {'data': [project(r, returning) for r in gone] if returning is not None else None}

    return err('Unsupported op ' + str(op))

def rpc_op(name, args, uid):
    if name == 'next_report_number':
        if not uid:
            return err('not signed in', '42501', 401)
        mx = max([r.get('report_number') or 0 for r in DB['tables']['reports'] if r.get('owner_id') == uid] + [0])
        n = max(mx, DB['counters'].get(uid, 0)) + 1
        DB['counters'][uid] = n
        return 200, {'data': n}
    if name == 'is_admin':
        return 200, {'data': is_admin(uid)}
    if name == 'increment_preset_copies':
        for r in DB['tables']['public_presets']:
            if r['id'] == (args or {}).get('preset_id'):
                r['copy_count'] = (r.get('copy_count') or 0) + 1
        return 200, {'data': None}
    if name == 'review_preset':
        if not is_admin(uid):
            return err('Only admins can review presets', '42501', 403)
        a = args or {}
        for r in DB['tables']['public_presets']:
            if r['id'] == a.get('preset_id'):
                r['review_state'] = a.get('new_state')
                r['review_note'] = a.get('note')
                r['updated_at'] = now_iso()
                return 200, {'data': None}
        return err('Preset not found', 'P0002', 404)
    return err('Could not find the function public.%s' % name, 'PGRST202', 404)

# ---------------------------------------------------------------- dashboard state

def read_json_dir(d):
    out = []
    if d.exists():
        for p in sorted(d.glob('*.json')):
            try:
                out.append(json.loads(p.read_text()))
            except Exception:
                pass
    return out

def state():
    t = DB['tables']
    pub = t['public_presets']
    preset_count = sum(len(r.get('data') or []) if isinstance(r.get('data'), list) else 0 for r in t['presets'])
    fixes = sorted(p.name for p in (BOARD / 'fixes').glob('*')) if (BOARD / 'fixes').exists() else []
    return {
        'now': now_iso(),
        'agents': read_json_dir(BOARD / 'agents'),
        'bugs': read_json_dir(BOARD / 'bugs'),
        'fixes': fixes,
        'mailbox': DB['mailbox'][-40:],
        'counts': {
            'accounts': len(DB['users']),
            'confirmed': sum(1 for u in DB['users'].values() if u.get('confirmed_at')),
            'reports': len(t['reports']),
            'presets': preset_count,
            'public_presets': len(pub),
            'approved_presets': sum(1 for r in pub if r.get('review_state') == 'approved'),
            'business_profiles': len(t['business_profile']),
            'media_files': sum(1 for _ in MEDIA.rglob('*') if _.is_file()) if MEDIA.exists() else 0,
            'api_calls': DB.get('requests', 0),
        },
    }

# ---------------------------------------------------------------- http

class H(BaseHTTPRequestHandler):
    server_version = 'LeakTraceQA/1.0'

    def log_message(self, fmt, *a):
        if os.environ.get('QUIET') != '1':
            sys.stderr.write('%s %s\n' % (self.address_string(), fmt % a))

    def _send(self, status, payload=None, raw=None, ctype='application/json'):
        body = raw if raw is not None else json.dumps(payload).encode()
        self.send_response(status)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET,POST,PUT,DELETE,OPTIONS')
        self.end_headers()
        self.wfile.write(body)

    def _uid(self):
        a = self.headers.get('Authorization') or ''
        tok = a[7:] if a.lower().startswith('bearer ') else ''
        return DB['tokens'].get(tok)

    def _body(self):
        n = int(self.headers.get('Content-Length') or 0)
        return self.rfile.read(n) if n else b''

    def do_OPTIONS(self):
        self._send(204, raw=b'')

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(u.path)
        if path in ('/', '/dashboard'):
            return self._file(HARNESS / 'dashboard.html')
        if path == '/api/state':
            with LOCK:
                return self._send(200, state())
        if path == '/mock/mailbox':
            q = urllib.parse.parse_qs(u.query)
            to = (q.get('to') or [''])[0].lower()
            with LOCK:
                return self._send(200, [m for m in DB['mailbox'] if not to or m['to'] == to])
        if path.startswith('/mock/media/'):
            q = urllib.parse.parse_qs(u.query)
            rel = path[len('/mock/media/'):]
            with LOCK:
                ok = DB['media_tokens'].get((q.get('token') or [''])[0]) == rel
            if not ok:
                return self._send(400, {'error': 'InvalidJWT', 'message': 'invalid signature'})
            return self._file(MEDIA / rel)
        if path.startswith('/site/'):
            return self._file(SITE / path[len('/site/'):])
        if path.startswith('/harness/'):
            return self._file(HARNESS / path[len('/harness/'):])
        if path.startswith('/fixes/'):
            return self._file(BOARD / 'fixes' / path[len('/fixes/'):], ctype='text/plain; charset=utf-8')
        return self._send(404, {'error': 'not found'})

    def _file(self, p, ctype=None):
        try:
            p = p.resolve()
            if not str(p).startswith(str(ROOT)) or not p.is_file():
                return self._send(404, {'error': 'not found'})
            ct = ctype or mimetypes.guess_type(str(p))[0] or 'application/octet-stream'
            if ct.startswith('text/') and 'charset' not in ct:
                ct += '; charset=utf-8'
            return self._send(200, raw=p.read_bytes(), ctype=ct)
        except Exception as e:
            return self._send(500, {'error': str(e)})

    def do_PUT(self):
        u = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(u.path)
        if path.startswith('/mock/storage/upload/'):
            rel = path[len('/mock/storage/upload/'):]          # bucket/owner/report/file
            with LOCK:
                uid = self._uid()
                parts = rel.split('/')
                if not uid or len(parts) < 3 or parts[1] != uid:
                    return self._send(403, {'error': {'message': 'new row violates row-level security policy', 'statusCode': '403'}})
                dest = MEDIA / rel
                if dest.exists() and urllib.parse.parse_qs(u.query).get('upsert', ['false'])[0] != 'true':
                    return self._send(409, {'error': {'message': 'The resource already exists', 'statusCode': '409'}})
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(self._body())
                DB['requests'] = DB.get('requests', 0) + 1
                save_db()
            return self._send(200, {'data': {'path': '/'.join(parts[1:])}})
        return self._send(404, {'error': 'not found'})

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        try:
            body = json.loads(self._body() or b'{}')
        except Exception:
            return self._send(400, {'error': {'message': 'bad json'}})
        with LOCK:
            uid = self._uid()
            DB['requests'] = DB.get('requests', 0) + 1
            if path.startswith('/mock/auth/'):
                status, out = auth_op(path[len('/mock/auth/'):], body, uid)
            elif path == '/mock/rest':
                status, out = table_op(body, uid)
            elif path.startswith('/mock/rpc/'):
                status, out = rpc_op(path[len('/mock/rpc/'):], body, uid)
            elif path == '/mock/storage/remove':
                n = 0
                for p in body.get('paths') or []:
                    parts = p.split('/')
                    if uid and parts and parts[0] == uid:
                        f = MEDIA / body.get('bucket', '') / p
                        if f.is_file():
                            f.unlink(); n += 1
                status, out = 200, {'data': [{'name': p} for p in (body.get('paths') or [])][:n]}
            elif path == '/mock/storage/sign':
                rel = body.get('bucket', '') + '/' + body.get('path', '')
                parts = (body.get('path') or '').split('/')
                owner_ok = uid and parts and (parts[0] == uid or any(
                    can_read('reports', r, uid) for r in DB['tables']['reports'] if r.get('owner_id') == parts[0]))
                if not owner_ok or not (MEDIA / rel).is_file():
                    status, out = 400, {'error': {'message': 'Object not found', 'statusCode': '404'}}
                else:
                    tok = secrets.token_urlsafe(16)
                    DB['media_tokens'][tok] = rel
                    host = self.headers.get('Host') or 'localhost:%d' % PORT
                    status, out = 200, {'data': {'signedUrl': 'http://%s/mock/media/%s?token=%s' % (host, urllib.parse.quote(rel), tok)}}
            else:
                status, out = 404, {'error': {'message': 'not found'}}
            save_db()
        return self._send(status, out)

def main():
    global DB
    MOCKDB.mkdir(exist_ok=True)
    MEDIA.mkdir(exist_ok=True)
    for d in ('agents', 'bugs', 'fixes'):
        (BOARD / d).mkdir(parents=True, exist_ok=True)
    if '--reset' in sys.argv:
        if DB_FILE.exists():
            DB_FILE.unlink()
        shutil.rmtree(MEDIA, ignore_errors=True)
        MEDIA.mkdir()
        print('mock database cleared')
        if '--serve' not in sys.argv:
            return
    DB = load_db()
    save_db()
    srv = ThreadingHTTPServer(('127.0.0.1', PORT), H)
    print('LeakTrace QA harness on http://localhost:%d  (dashboard: /, app: /site/)' % PORT, flush=True)
    srv.serve_forever()

if __name__ == '__main__':
    main()
