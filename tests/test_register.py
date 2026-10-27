import base64
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
import uuid
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import server


def entry(**overrides):
    return {'request_id': str(uuid.uuid4()), 'calling_helpline': 'H3',
            'victim_name': 'Test Person', 'dob': '1990-05-24', 'pin': 'A A 382210',
            'mo': 'Test incident only', 'mobile': '9000000000',
            'notice_helpline': 'SM', 'remarks': 'Original note', **overrides}


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.conn = server.open_database()
        self.record = server.create_entry(self.conn, entry(), 'operator1')
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_every_entry_detail_is_locked(self):
        replacements = {'id': 99, 'request_id': str(uuid.uuid4()), 'calling_helpline': 'H2',
                        'victim_name': 'Changed name', 'dob': '2000-01-01', 'pin': '1',
                        'recorded_at': '2000-01-01', 'mo': 'Changed', 'mobile': '9111111111',
                        'notice_helpline': 'H5', 'created_by': 'other'}
        for field, value in replacements.items():
            with self.subTest(field=field), self.assertRaises(sqlite3.IntegrityError):
                self.conn.execute(f'UPDATE entries SET {field}=?, remarks_version=1, remarks_updated_at=?, remarks_updated_by=? WHERE id=1',
                                  (value, server.now_ist(), 'operator1'))
        self.assertEqual(dict(self.conn.execute('SELECT * FROM entries').fetchone()), self.record)

    def test_entry_cannot_be_deleted_or_replaced(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute('DELETE FROM entries')
        original = self.conn.execute('SELECT * FROM entries').fetchone()
        columns = ','.join(original.keys())
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(f'INSERT OR REPLACE INTO entries ({columns}) VALUES ({",".join("?" for _ in original)})', tuple(original))

    def test_remark_history_preserves_old_values_and_unicode(self):
        updated = server.update_remark(self.conn, 1, {'remarks': 'ફોલો અપ ✓', 'version': 0}, 'operator2')
        self.assertEqual(updated['remarks_version'], 1)
        history = self.conn.execute('SELECT * FROM remark_history').fetchone()
        self.assertEqual(history['old_remarks'], 'Original note')
        self.assertEqual(history['new_remarks'], 'ફોલો અપ ✓')
        self.assertEqual(history['changed_by'], 'operator2')
        self.assertTrue(history['changed_at'].endswith('+05:30'))
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute('DELETE FROM remark_history')
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("UPDATE remark_history SET new_remarks='tampered'")

    def test_remark_conflict_does_not_overwrite_newer_value(self):
        server.update_remark(self.conn, 1, {'remarks': 'First editor', 'version': 0}, 'operator1')
        with self.assertRaises(server.APIError) as result:
            server.update_remark(self.conn, 1, {'remarks': 'Second editor', 'version': 0}, 'operator2')
        self.assertEqual(result.exception.status, 409)
        self.assertEqual(self.conn.execute('SELECT remarks FROM entries').fetchone()[0], 'First editor')

    def test_duplicate_new_entry_retry_is_idempotent(self):
        body = entry()
        first = server.create_entry(self.conn, body, 'operator1')
        second = server.create_entry(self.conn, body, 'operator1')
        self.assertEqual(first, second)
        self.assertEqual(self.conn.execute('SELECT count(*) FROM entries').fetchone()[0], 2)

    def test_remark_retry_and_no_op_do_not_duplicate_history(self):
        body = {'remarks': 'Updated', 'version': 0}
        first = server.update_remark(self.conn, 1, body, 'operator1')
        self.assertEqual(server.update_remark(self.conn, 1, body, 'operator1'), first)
        server.update_remark(self.conn, 1, {'remarks': 'Updated', 'version': 1}, 'operator1')
        self.assertEqual(self.conn.execute('SELECT count(*) FROM remark_history').fetchone()[0], 1)

    def test_retry_with_different_locked_details_is_rejected(self):
        body = entry()
        server.create_entry(self.conn, body, 'operator1')
        with self.assertRaises(server.APIError) as result:
            server.create_entry(self.conn, {**body, 'victim_name': 'A different person'}, 'operator1')
        self.assertEqual(result.exception.status, 409)

    def test_patch_rejects_extra_fields_and_wrong_version_types(self):
        for body in ({'remarks': 'x', 'version': 0, 'victim_name': 'Changed'},
                     {'remarks': 'x', 'version': True}, {'remarks': 'x', 'version': -1},
                     {'remarks': 'x' * 5001, 'version': 0}):
            with self.subTest(body_type=type(body)), self.assertRaises(server.APIError):
                server.update_remark(self.conn, 1, body, 'operator1')

    def test_search_filters_and_literal_wildcards(self):
        server.create_entry(self.conn, entry(victim_name='નામ Test', mo='100% test_underscore'), 'operator1')
        rows, count = server.query_entries(self.conn, {'q': ['100%']})
        self.assertEqual(count, 1)
        self.assertEqual(rows[0]['victim_name'], 'નામ Test')
        self.assertEqual(server.query_entries(self.conn, {'q': ['_underscore']})[1], 1)
        self.assertEqual(server.query_entries(self.conn, {'helpline': ['SM']})[1], 2)
        self.assertEqual(server.query_entries(self.conn, {'helpline': ['H20']})[1], 0)
        self.assertEqual(server.query_entries(self.conn, {'to': ['2000-01-01']})[1], 0)
        with self.assertRaises(server.APIError):
            server.query_entries(self.conn, {'from': ['invalid']})

    def test_validation_rejects_invalid_details(self):
        for changes in ({'dob': '2099-01-01'}, {'dob': '1990-02-30'}, {'mobile': '123'},
                        {'mobile': 'abcdefghij'}, {'victim_name': 'x'}, {'mo': ''},
                        {'calling_helpline': 'H99'}, {'created_by': 'forged'}):
            with self.subTest(changes=changes), self.assertRaises(server.APIError):
                server.validate_entry(entry(**changes))

    def test_sqlite_serialization_retains_locks_and_history(self):
        server.update_remark(self.conn, 1, {'remarks': 'Changed', 'version': 0}, 'operator1')
        self.conn.commit()
        restored = server.open_database(self.conn.serialize())
        try:
            self.assertEqual(restored.execute('SELECT count(*) FROM remark_history').fetchone()[0], 1)
            with self.assertRaises(sqlite3.IntegrityError):
                restored.execute('DELETE FROM entries')
        finally:
            restored.close()


class SimulatedGitHub(server.GitHubStore):
    def __init__(self, race=False, private=True, inline=True):
        super().__init__('test/private-data', 'not-a-real-token')
        self.data, self.sha = None, None
        self.race, self.private, self.inline = race, private, inline
        self.commits = 0

    def replace_database(self, body):
        self.data = body
        self.sha = hashlib.sha1(body).hexdigest()

    def request(self, method, endpoint, body=None, raw=False):
        if method == 'GET' and endpoint == '':
            return {'private': self.private}
        if method == 'GET' and endpoint.startswith('/branches/'):
            return {'name': 'main'}
        if method == 'GET' and endpoint.startswith('/git/blobs/'):
            return self.data
        if method == 'GET':
            if not self.data:
                raise HTTPError(endpoint, 404, 'Not Found', {}, io.BytesIO())
            return {'type': 'file', 'sha': self.sha, 'size': len(self.data),
                    'encoding': 'base64' if self.inline else 'none',
                    'content': base64.b64encode(self.data).decode() if self.inline else ''}
        if self.race:
            self.race = False
            conn = server.open_database(self.data)
            server.create_entry(conn, entry(victim_name='Concurrent Operator Entry'), 'operator2')
            conn.commit()
            self.replace_database(conn.serialize())
            conn.close()
        if body.get('sha') != self.sha:
            raise HTTPError(endpoint, 409, 'Conflict', {}, io.BytesIO())
        self.replace_database(base64.b64decode(body['content']))
        self.commits += 1
        return {'content': {'sha': self.sha}}


class GitHubTests(unittest.TestCase):
    def test_placeholder_secrets_are_rejected(self):
        with self.assertRaises(ValueError):
            server.GitHubStore('test/private-data', 'REPLACE-WITH-FINE-GRAINED-TOKEN')
        with self.assertRaises(ValueError):
            server.App(server.LocalStore('unused'), {'operator1': 'REPLACE-WITH-LONG-PASSWORD'}, 's' * 48, [])
        with self.assertRaises(ValueError):
            server.App(server.LocalStore('unused'), {'operator1': 'a-long-test-password'}, 'REPLACE-WITH-A-LONG-SECRET-OF-32-CHARACTERS', [])

    def test_conflict_reloads_database_and_preserves_both_records(self):
        store = SimulatedGitHub(race=True)
        body = entry()
        result = store.mutate(lambda conn: server.create_entry(conn, body, 'operator1'), 'Register entry')
        self.assertEqual(result['id'], 2)
        conn = server.open_database(store.read())
        self.assertEqual(conn.execute('SELECT count(*) FROM entries').fetchone()[0], 2)
        conn.close()

    def test_repeated_save_does_not_commit_again(self):
        store = SimulatedGitHub()
        body = entry()
        store.mutate(lambda conn: server.create_entry(conn, body, 'operator1'), 'Register entry')
        store.mutate(lambda conn: server.create_entry(conn, body, 'operator1'), 'Register entry')
        self.assertEqual(store.commits, 1)

    def test_public_repository_is_rejected(self):
        with self.assertRaises(server.APIError) as result:
            SimulatedGitHub(private=False).read()
        self.assertEqual(result.exception.status, 503)

    def test_larger_database_raw_blob_fallback(self):
        store = SimulatedGitHub(inline=False)
        conn = server.open_database()
        conn.commit()
        store.replace_database(conn.serialize())
        conn.close()
        self.assertTrue(store.read().startswith(b'SQLite format 3\x00'))


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.store = server.LocalStore(Path(cls.directory.name) / 'test.sqlite3')
        cls.app = server.App(cls.store, {'operator1': 'test-password-12345'}, 's' * 48, ['https://test.github.io'])
        cls.http = server.make_server(cls.app, port=0)
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f'http://127.0.0.1:{cls.http.server_port}'
        cls.token = cls.request('POST', '/api/login', {'username': 'operator1', 'password': 'test-password-12345'})[1]['token']

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.thread.join()
        cls.directory.cleanup()

    @classmethod
    def request(cls, method, path, body=None, auth=False, origin=None):
        headers = {'Content-Type': 'application/json'}
        if auth:
            headers['Authorization'] = 'Bearer ' + cls.token
        if origin:
            headers['Origin'] = origin
        req = Request(cls.base + path, data=json.dumps(body).encode() if body is not None else None,
                      headers=headers, method=method)
        try:
            response = urlopen(req, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            raw = response.read()
            payload = json.loads(raw) if raw and 'application/json' in response.headers.get('Content-Type', '') else raw
            return response.status, payload, response.headers

    def test_unauthenticated_requests_and_wrong_origin_are_blocked(self):
        self.assertEqual(self.request('GET', '/api/entries')[0], 401)
        self.assertEqual(self.request('GET', '/api/export?format=sqlite')[0], 401)
        self.assertEqual(self.request('GET', '/api/entries', auth=True, origin='https://evil.example')[0], 403)
        status, _, headers = self.request('OPTIONS', '/api/entries', origin='https://test.github.io')
        self.assertEqual(status, 204)
        self.assertEqual(headers['Access-Control-Allow-Origin'], 'https://test.github.io')

    def test_only_remark_update_endpoint_is_allowed(self):
        status, record, _ = self.request('POST', '/api/entries', entry(), True)
        self.assertEqual(status, 201)
        path = '/api/entries/' + str(record['id'])
        self.assertEqual(self.request('DELETE', path, auth=True)[0], 405)
        self.assertEqual(self.request('PUT', path, {'victim_name': 'Changed'}, True)[0], 405)
        self.assertEqual(self.request('PATCH', path + '/remarks', {'remarks': 'New note', 'version': 0}, True)[0], 200)
        status, history, _ = self.request('GET', path + '/history', auth=True)
        self.assertEqual(status, 200)
        self.assertEqual(history['entry']['remarks'], 'New note')
        self.assertEqual(history['entry']['remarks_version'], 1)
        self.assertEqual(history['history'][0]['old_remarks'], 'Original note')
        self.assertEqual(self.request('PATCH', path + '/remarks', {'remarks': 'New note', 'version': 1, 'pin': 'Changed'}, True)[0], 400)

    def test_exports_include_all_pages_and_valid_sqlite(self):
        def seed(conn):
            for i in range(65):
                server.create_entry(conn, entry(victim_name=f'Export Test {i}', remarks='=1+1' if i == 0 else 'ગુજરાતી'), 'operator1')
        self.store.mutate(seed, 'Test fixture')
        status, listing, _ = self.request('GET', '/api/entries', auth=True)
        self.assertEqual(status, 200)
        self.assertEqual(len(listing['entries']), 50)
        status, archive, _ = self.request('GET', '/api/export?format=json', auth=True)
        self.assertEqual(len(archive['entries']), listing['total_entries'])
        self.assertGreater(len(archive['entries']), 50)
        status, filtered, _ = self.request('GET', '/api/export?format=json&q=Export%20Test', auth=True)
        self.assertEqual(len(filtered['entries']), 65)
        status, csv_file, _ = self.request('GET', '/api/export?format=csv', auth=True)
        self.assertTrue(csv_file.startswith(b'\xef\xbb\xbf'))
        self.assertIn("'=1+1", csv_file.decode('utf-8-sig'))
        self.assertIn('ગુજરાતી', csv_file.decode('utf-8-sig'))
        status, database, _ = self.request('GET', '/api/export?format=sqlite', auth=True)
        conn = server.open_database(database)
        self.assertEqual(conn.execute('SELECT count(*) FROM entries').fetchone()[0], listing['total_entries'])
        conn.close()

    def test_expired_or_modified_session_is_rejected(self):
        with self.assertRaises(server.APIError):
            self.app.authenticate('Bearer operator1:1:invalid')
        with self.assertRaises(server.APIError):
            self.app.authenticate('Bearer ' + self.token + 'tampered')

    def test_failed_login_is_throttled(self):
        for _ in range(5):
            with self.assertRaises(server.APIError) as result:
                self.app.login({'username': 'operator1', 'password': 'wrong'}, 'test-ip')
            self.assertEqual(result.exception.status, 401)
        with self.assertRaises(server.APIError) as result:
            self.app.login({'username': 'operator1', 'password': 'test-password-12345'}, 'test-ip')
        self.assertEqual(result.exception.status, 429)


if __name__ == '__main__':
    unittest.main()
