"""Helpline 1930 API. Python 3.11+, standard library only.

GitHub is the authoritative SQLite store in github mode. Each mutation commits
the whole database with a compare-and-swap SHA. Never expose GITHUB_TOKEN to HTML.
"""
from __future__ import annotations

import base64
import csv
import hashlib
import hmac
import io
import json
import logging
import os
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import time
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
IST = timezone(timedelta(hours=5, minutes=30))
SCHEMA = (Path(__file__).with_name('schema.sql')).read_text(encoding='utf-8')
MAX_DATABASE_BYTES = 20 * 1024 * 1024
HELPLINES = {'', 'SM', *(f'H{i}' for i in range(1, 21))}
ENTRY_FIELDS = {'request_id', 'calling_helpline', 'victim_name', 'dob', 'pin',
                'mo', 'mobile', 'notice_helpline', 'remarks'}
EXPORT_FIELDS = [('id', 'Entry ID'), ('calling_helpline', 'Calling helpline'),
                 ('victim_name', 'Victim name'), ('dob', 'DOB'), ('pin', 'PIN'),
                 ('recorded_at', 'Date (IST)'), ('mo', 'MO'), ('mobile', 'Mobile no'),
                 ('notice_helpline', 'Notice helpline'), ('created_by', 'Created by'),
                 ('remarks_version', 'Remarks version'),
                 ('remarks_updated_at', 'Remarks updated at'),
                 ('remarks_updated_by', 'Remarks updated by'), ('remarks', 'Remarks')]


class APIError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def load_env():
    """Small .env reader; existing process environment always wins."""
    path = ROOT / '.env'
    if path.exists():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip().strip('\"').strip("'"))


def now_ist():
    return datetime.now(IST).isoformat(timespec='seconds')


def open_database(data=None):
    conn = sqlite3.connect(':memory:')
    if data:
        if not data.startswith(b'SQLite format 3\x00'):
            raise APIError(503, 'The configured file is not a SQLite database.')
        conn.deserialize(data)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    conn.execute('PRAGMA recursive_triggers = ON')
    conn.executescript(SCHEMA)
    return conn


class LocalStore:
    mode = 'local'

    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.Lock()

    def read(self):
        with self.lock:
            return self.path.read_bytes() if self.path.exists() else None

    def mutate(self, operation, message):
        with self.lock:
            conn = open_database(self.path.read_bytes() if self.path.exists() else None)
            try:
                result = operation(conn)
                conn.commit()
                self.path.parent.mkdir(parents=True, exist_ok=True)
                temporary = self.path.with_suffix('.tmp')
                temporary.write_bytes(conn.serialize())
                temporary.replace(self.path)
                return result
            finally:
                conn.close()


class GitHubStore:
    mode = 'github'

    def __init__(self, repo, token, branch='main', path='data/helpline.sqlite3'):
        if not re.fullmatch(r'[\w.-]+/[\w.-]+', repo):
            raise ValueError('GITHUB_REPO must be OWNER/PRIVATE-REPOSITORY')
        if not token or token.upper().startswith('REPLACE-'):
            raise ValueError('Set GITHUB_TOKEN to your private repository token on the server.')
        self.base = f'https://api.github.com/repos/{repo}'
        self.token, self.branch, self.path = token, branch, path
        self.lock = threading.Lock()

    def request(self, method, endpoint, body=None, raw=False):
        headers = {'Authorization': f'Bearer {self.token}',
                   'Accept': 'application/vnd.github.raw+json' if raw else 'application/vnd.github+json',
                   'X-GitHub-Api-Version': '2022-11-28',
                   'User-Agent': 'helpline-1930-register',
                   'Cache-Control': 'no-cache'}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers['Content-Type'] = 'application/json'
        try:
            with urlopen(Request(self.base + endpoint, data=data, headers=headers, method=method), timeout=30) as response:
                payload = response.read(MAX_DATABASE_BYTES + 1024 * 1024)
                if raw:
                    if len(payload) > MAX_DATABASE_BYTES:
                        raise APIError(507, 'Database exceeds the configured 20 MB limit. Contact the administrator.')
                    return payload
                return json.loads(payload)
        except HTTPError:
            raise
        except (URLError, TimeoutError, OSError, ValueError) as exc:
            raise APIError(503, 'GitHub storage is unavailable. No save was confirmed; retry safely.') from exc

    def snapshot(self):
        # Check privacy on every snapshot; never write victim records to a public repository.
        try:
            repository = self.request('GET', '')
            if repository.get('private') is not True:
                raise APIError(503, 'The database repository must be private. Ask the administrator to fix storage.')
            self.request('GET', '/branches/' + quote(self.branch, safe=''))
        except HTTPError as exc:
            raise APIError(503, 'Cannot access the private data repository or branch. Check the server configuration.') from exc
        endpoint = '/contents/' + quote(self.path, safe='/')
        try:
            item = self.request('GET', endpoint + '?ref=' + quote(self.branch, safe=''))
        except HTTPError as exc:
            if exc.code == 404:
                return None, None
            self.storage_error(exc)
        if item.get('type') != 'file' or item.get('size', 0) > MAX_DATABASE_BYTES:
            raise APIError(507, 'The configured database file is invalid or exceeds 20 MB.')
        if item.get('encoding') == 'base64':
            data = base64.b64decode(item['content'])
        else:
            try:
                data = self.request('GET', '/git/blobs/' + item['sha'], raw=True)
            except HTTPError as exc:
                self.storage_error(exc)
        return data, item['sha']

    @staticmethod
    def storage_error(exc):
        if exc.code in (403, 429):
            raise APIError(503, 'GitHub denied access or its rate limit was reached. Please retry later.') from exc
        raise APIError(503, 'GitHub storage rejected the request. Check the server configuration.') from exc

    def read(self):
        return self.snapshot()[0]

    def mutate(self, operation, message):
        with self.lock:
            for _ in range(4):
                data, sha = self.snapshot()
                conn = open_database(data)
                try:
                    result = operation(conn)
                    conn.commit()
                    updated = conn.serialize()
                finally:
                    conn.close()
                if len(updated) > MAX_DATABASE_BYTES:
                    raise APIError(507, 'The SQLite database has reached its configured 20 MB limit.')
                if data == updated:
                    return result
                body = {'message': message, 'content': base64.b64encode(updated).decode(), 'branch': self.branch}
                if sha:
                    body['sha'] = sha
                try:
                    self.request('PUT', '/contents/' + quote(self.path, safe='/'), body)
                    return result
                except HTTPError as exc:
                    if exc.code in (409, 422):
                        continue  # Reload the latest SQLite file and reapply the operation.
                    self.storage_error(exc)
            raise APIError(409, 'Another user is saving. Please retry; no save was confirmed.')


def validate_entry(body):
    if not isinstance(body, dict) or set(body) - ENTRY_FIELDS:
        raise APIError(400, 'Unknown entry fields. Saved details cannot be edited.')
    result = {}
    limits = {'request_id': 36, 'victim_name': 120, 'dob': 10, 'pin': 80,
              'mo': 3000, 'mobile': 25, 'remarks': 5000,
              'calling_helpline': 3, 'notice_helpline': 3}
    for key, limit in limits.items():
        value = body.get(key, '')
        if not isinstance(value, str) or len(value.strip()) > limit or '\x00' in value:
            raise APIError(400, f'Invalid {key.replace("_", " ")}.')
        result[key] = value.strip()
    if not re.fullmatch(r'[a-f0-9-]{36}', result['request_id']):
        raise APIError(400, 'A valid submission ID is required.')
    if len(result['victim_name']) < 2 or not result['mo']:
        raise APIError(400, 'Victim name and MO are required.')
    if not re.fullmatch(r'\+?[0-9 ()-]+', result['mobile']):
        raise APIError(400, 'Enter a valid mobile number.')
    digits = re.sub(r'\D', '', result['mobile'])
    if not 10 <= len(digits) <= 15:
        raise APIError(400, 'Mobile number must contain 10 to 15 digits.')
    if result['dob']:
        try:
            dob = date.fromisoformat(result['dob'])
            if dob > datetime.now(IST).date() or dob.year < 1900:
                raise ValueError()
        except ValueError as exc:
            raise APIError(400, 'DOB must be a valid date from 1900 through today.') from exc
    for field in ('calling_helpline', 'notice_helpline'):
        if result[field] not in HELPLINES:
            raise APIError(400, 'Select a valid helpline.')
    return result


def create_entry(conn, body, user):
    entry = validate_entry(body)
    existing = conn.execute('SELECT * FROM entries WHERE request_id=?', (entry['request_id'],)).fetchone()
    if existing:
        if existing['created_by'] != user or any(existing[key] != value for key, value in entry.items() if key != 'remarks'):
            raise APIError(409, 'This submission was already saved with different details. Close the form and refresh the register to verify it before adding anything else.')
        return dict(existing)  # Safe retry after a lost network response; never duplicates a save.
    columns = list(entry) + ['recorded_at', 'created_by']
    values = list(entry.values()) + [now_ist(), user]
    cursor = conn.execute(f'INSERT INTO entries ({",".join(columns)}) VALUES ({",".join("?" for _ in columns)})', values)
    return dict(conn.execute('SELECT * FROM entries WHERE id=?', (cursor.lastrowid,)).fetchone())


def update_remark(conn, entry_id, body, user):
    if not isinstance(body, dict) or set(body) != {'remarks', 'version'}:
        raise APIError(400, 'Only remarks and its version may be submitted.')
    remarks, version = body['remarks'], body['version']
    if not isinstance(remarks, str) or len(remarks) > 5000 or '\x00' in remarks:
        raise APIError(400, 'Remarks must contain at most 5,000 characters.')
    if type(version) is not int or version < 0:
        raise APIError(400, 'Invalid remarks version.')
    row = conn.execute('SELECT * FROM entries WHERE id=?', (entry_id,)).fetchone()
    if not row:
        raise APIError(404, 'Entry not found.')
    if row['remarks_version'] != version:
        # A repeat of the same already-applied save is safe after a timeout.
        if row['remarks_version'] == version + 1 and row['remarks'] == remarks and row['remarks_updated_by'] == user:
            return dict(row)
        raise APIError(409, 'Someone has updated these remarks. Close and reopen the editor to load the latest version; copy your draft first.')
    if row['remarks'] == remarks:
        return dict(row)
    conn.execute('UPDATE entries SET remarks=?, remarks_version=remarks_version+1, remarks_updated_at=?, remarks_updated_by=? WHERE id=?',
                 (remarks, now_ist(), user, entry_id))
    return dict(conn.execute('SELECT * FROM entries WHERE id=?', (entry_id,)).fetchone())


def query_entries(conn, query, paginate=True):
    conditions, values = [], []
    search = query.get('q', [''])[0].strip()
    if len(search) > 200:
        raise APIError(400, 'Search is too long.')
    if search:
        conditions.append('(' + ' OR '.join(f'{field} LIKE ? ESCAPE \'\\\'' for field in
                          ('victim_name', 'mobile', 'pin', 'mo', 'remarks', 'created_by', 'CAST(id AS TEXT)')) + ')')
        literal = search.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        values.extend([f'%{literal}%'] * 7)
    for key, operator in (('from', '>='), ('to', '<=')):
        value = query.get(key, [''])[0]
        if value:
            try:
                date.fromisoformat(value)
            except ValueError as exc:
                raise APIError(400, 'Invalid date filter.') from exc
            conditions.append(f'substr(recorded_at, 1, 10) {operator} ?')
            values.append(value)
    helpline = query.get('helpline', [''])[0]
    if helpline:
        if helpline not in HELPLINES:
            raise APIError(400, 'Invalid helpline filter.')
        conditions.append('(calling_helpline=? OR notice_helpline=?)')
        values.extend([helpline, helpline])
    where = ' WHERE ' + ' AND '.join(conditions) if conditions else ''
    total = conn.execute('SELECT count(*) FROM entries' + where, values).fetchone()[0]
    sql = 'SELECT * FROM entries' + where + ' ORDER BY id DESC'
    if paginate:
        try:
            page = max(1, int(query.get('page', ['1'])[0]))
        except ValueError as exc:
            raise APIError(400, 'Invalid page.') from exc
        sql += ' LIMIT 50 OFFSET ?'
        values.append((page - 1) * 50)
    return [dict(row) for row in conn.execute(sql, values)], total


def safe_csv(value):
    value = '' if value is None else str(value)
    # Prevent spreadsheet formulas, including values prefixed by control characters.
    if value.lstrip().startswith(('=', '+', '-', '@')) or value.startswith(('\t', '\r', '\n')):
        return "'" + value
    return value


class App:
    def __init__(self, store, users, session_secret, origins):
        if not users or not all(re.fullmatch(r'[A-Za-z0-9_.-]{2,50}', name) and isinstance(password, str) and len(password) >= 12 and not password.upper().startswith('REPLACE-')
                                for name, password in users.items()):
            raise ValueError('USERS_JSON must map usernames (2-50 letters/digits/_.-) to passwords of 12+ characters.')
        if len(session_secret) < 32 or session_secret.upper().startswith('REPLACE-'):
            raise ValueError('SESSION_SECRET must be a unique secret of at least 32 characters; replace example values.')
        self.store, self.users, self.secret, self.origins = store, users, session_secret.encode(), set(origins)
        self.failures, self.auth_lock = {}, threading.Lock()

    def signature(self, payload, user):
        return hmac.new(self.secret, payload.encode() + hashlib.sha256(self.users[user].encode()).digest(), hashlib.sha256).hexdigest()

    def login(self, body, ip):
        if not isinstance(body, dict):
            raise APIError(400, 'Invalid sign-in request.')
        user, password = body.get('username', ''), body.get('password', '')
        if not isinstance(user, str) or not isinstance(password, str):
            raise APIError(400, 'Invalid sign-in request.')
        current = time.time()
        with self.auth_lock:
            self.failures = {key: item for key, item in self.failures.items() if current - item[0] < 300}
            failed = self.failures.get(ip, (current, 0))
            if failed[1] >= 5:
                raise APIError(429, 'Too many sign-in attempts. Wait five minutes.')
            valid = hmac.compare_digest(hashlib.sha256(password.encode()).digest(),
                                        hashlib.sha256(self.users.get(user, secrets.token_hex(32)).encode()).digest())
            if user not in self.users or not valid:
                self.failures[ip] = (failed[0], failed[1] + 1)
                raise APIError(401, 'Incorrect username or password.')
            self.failures.pop(ip, None)
        expiry = int(current) + 12 * 60 * 60
        payload = f'{user}:{expiry}'
        return {'token': payload + ':' + self.signature(payload, user), 'username': user, 'expires_at': expiry,
                'storage': self.store.mode}

    def authenticate(self, header):
        try:
            if not header.startswith('Bearer '):
                raise ValueError()
            token = header[7:]
            user, expiry, signature = token.split(':')
            if user not in self.users or int(expiry) <= time.time() or not hmac.compare_digest(signature, self.signature(f'{user}:{expiry}', user)):
                raise ValueError()
            return user
        except (ValueError, TypeError):
            raise APIError(401, 'Your session has expired. Please sign in again.') from None


class Handler(BaseHTTPRequestHandler):
    server_version = 'Helpline1930'
    app: App

    def log_message(self, format, *args):
        # No URLs, search terms, tokens, passwords, or victim details in access logs.
        pass

    def respond(self, status, payload, content_type='application/json; charset=utf-8', filename=None):
        data = json.dumps(payload, ensure_ascii=False).encode() if isinstance(payload, (dict, list)) else payload
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Vary', 'Origin')
        origin = self.headers.get('Origin', '')
        if origin in self.app.origins:
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, PATCH, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Authorization, Content-Type')
            self.send_header('Access-Control-Expose-Headers', 'Content-Disposition')
        if filename:
            self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(data)

    def body(self):
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length < 1 or length > 65536:
                raise APIError(413, 'Request body must be between 1 byte and 64 KB.')
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                raise APIError(415, 'Send application/json.')
            return json.loads(self.rfile.read(length))
        except (ValueError, UnicodeError) as exc:
            raise APIError(400, 'Invalid JSON request.') from exc

    def do_OPTIONS(self):
        self.dispatch('OPTIONS')

    def do_GET(self):
        self.dispatch('GET')

    def do_POST(self):
        self.dispatch('POST')

    def do_PATCH(self):
        self.dispatch('PATCH')

    def do_PUT(self):
        self.dispatch('PUT')

    def do_DELETE(self):
        self.dispatch('DELETE')

    def dispatch(self, method):
        try:
            origin = self.headers.get('Origin')
            if origin and origin not in self.app.origins:
                raise APIError(403, 'This website origin is not allowed.')
            if method == 'OPTIONS':
                return self.respond(204, b'')
            parsed = urlparse(self.path)
            path, query = parsed.path, parse_qs(parsed.query)
            if path == '/health' and method == 'GET':
                return self.respond(200, {'status': 'ok', 'storage': self.app.store.mode})
            if path in ('/', '/index.html') and method == 'GET':
                return self.respond(200, (ROOT / 'index.html').read_bytes(), 'text/html; charset=utf-8')
            if path == '/api/login' and method == 'POST':
                return self.respond(200, self.app.login(self.body(), self.client_address[0]))
            user = self.app.authenticate(self.headers.get('Authorization', ''))
            if path == '/api/me' and method == 'GET':
                return self.respond(200, {'username': user, 'storage': self.app.store.mode})
            if path == '/api/entries' and method == 'POST':
                body = self.body()
                result = self.app.store.mutate(lambda conn: create_entry(conn, body, user), 'Register entry')
                return self.respond(201, result)
            match = re.fullmatch(r'/api/entries/(\d+)/remarks', path)
            if match and method == 'PATCH':
                body = self.body()
                result = self.app.store.mutate(lambda conn: update_remark(conn, int(match[1]), body, user), 'Update entry remarks')
                return self.respond(200, result)
            if method != 'GET':
                raise APIError(405, 'This action is not allowed. Saved entries cannot be deleted or changed; only remarks may be updated.')
            conn = open_database(self.app.store.read())
            try:
                if path == '/api/entries':
                    entries, total = query_entries(conn, query)
                    today = datetime.now(IST).date().isoformat()
                    stats = conn.execute('SELECT count(*), coalesce(sum(substr(recorded_at,1,10)=?),0) FROM entries', (today,)).fetchone()
                    return self.respond(200, {'entries': entries, 'total': total, 'total_entries': stats[0],
                                              'today_entries': stats[1], 'page_size': 50, 'storage': self.app.store.mode})
                match = re.fullmatch(r'/api/entries/(\d+)/history', path)
                if match:
                    entry = conn.execute('SELECT * FROM entries WHERE id=?', (int(match[1]),)).fetchone()
                    if not entry:
                        raise APIError(404, 'Entry not found.')
                    rows = conn.execute('SELECT * FROM remark_history WHERE entry_id=? ORDER BY version DESC', (int(match[1]),))
                    return self.respond(200, {'entry': dict(entry), 'history': [dict(row) for row in rows]})
                if path == '/api/export':
                    kind = query.get('format', ['csv'])[0]
                    filename = 'helpline-1930-' + datetime.now(IST).strftime('%Y-%m-%d')
                    if kind == 'sqlite':
                        return self.respond(200, conn.serialize(), 'application/vnd.sqlite3', filename + '.sqlite3')
                    entries, _ = query_entries(conn, query, paginate=False)
                    if kind == 'json':
                        history = [dict(row) for row in conn.execute('SELECT * FROM remark_history ORDER BY id')]
                        selected_ids = {row['id'] for row in entries}
                        return self.respond(200, {'exported_at': now_ist(), 'entries': entries,
                                                  'remark_history': [row for row in history if row['entry_id'] in selected_ids]},
                                            filename=filename + '.json')
                    if kind == 'csv':
                        output = io.StringIO(newline='')
                        writer = csv.writer(output)
                        writer.writerow([label for _, label in EXPORT_FIELDS])
                        writer.writerows([[safe_csv(row[key]) for key, _ in EXPORT_FIELDS] for row in entries])
                        return self.respond(200, ('\ufeff' + output.getvalue()).encode(), 'text/csv; charset=utf-8', filename + '.csv')
                    raise APIError(400, 'Select CSV, JSON, or SQLite export.')
                raise APIError(404, 'Endpoint not found.')
            finally:
                conn.close()
        except APIError as exc:
            self.respond(exc.status, {'error': exc.message})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            logging.exception('API request failed')
            self.respond(500, {'error': 'The server could not complete the request. No save was confirmed; retry safely.'})


def make_server(app, host='127.0.0.1', port=8000):
    handler = type('ConfiguredHandler', (Handler,), {'app': app})
    server = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    return server


def main():
    load_env()
    users = json.loads(os.environ.get('USERS_JSON', '{}'))
    mode = os.environ.get('STORAGE_MODE', 'github')
    if mode == 'local':
        store = LocalStore(os.environ.get('SQLITE_PATH', str(ROOT / 'data' / 'helpline.sqlite3')))
    elif mode == 'github':
        store = GitHubStore(os.environ.get('GITHUB_REPO', ''), os.environ['GITHUB_TOKEN'],
                            os.environ.get('GITHUB_BRANCH', 'main'), os.environ.get('GITHUB_DB_PATH', 'data/helpline.sqlite3'))
    else:
        raise ValueError('STORAGE_MODE must be github or local.')
    origins = [value.strip().rstrip('/') for value in os.environ.get('ALLOWED_ORIGINS', 'http://localhost:8000,http://127.0.0.1:8000').split(',') if value.strip()]
    app = App(store, users, os.environ.get('SESSION_SECRET', ''), origins)
    host, port = os.environ.get('HOST', '127.0.0.1'), int(os.environ.get('PORT', '8000'))
    print(f'Helpline 1930: http://{host}:{port} | SQLite storage: {mode}', flush=True)
    make_server(app, host, port).serve_forever()


if __name__ == '__main__':
    main()
