"""Local, source-grouped human review. Choices are separate from worker acceptance."""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
import csv
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import time
from urllib.parse import urlsplit


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def plain(text):
    return re.sub(r'<[^>]*>', '', text or '').strip()


class Conflict(ValueError):
    pass


class ReviewStore:
    def __init__(self, run, output):
        self.run = Path(run).resolve()
        self.output = Path(output).resolve()
        self.output.mkdir(parents=True, exist_ok=True)
        self.database = self.output / 'feedback.sqlite'
        self.mutex = threading.RLock()
        descriptor = read_json(self.run / 'run.json')
        self.baseline = Path(descriptor['baseline']).resolve()
        self.candidate = Path(descriptor['candidate']).resolve()
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS items(
                    id TEXT PRIMARY KEY, payload TEXT NOT NULL, imported REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS decisions(
                    item_id TEXT PRIMARY KEY REFERENCES items(id),
                    choice TEXT CHECK(choice IS NULL OR choice IN ('keep','redo')),
                    note TEXT NOT NULL, revision INTEGER NOT NULL, updated REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS events(
                    id INTEGER PRIMARY KEY, item_id TEXT NOT NULL REFERENCES items(id),
                    choice TEXT, note TEXT NOT NULL, revision INTEGER NOT NULL, created REAL NOT NULL);
            ''')
        self.refresh()

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    @contextmanager
    def ledger(self):
        db = sqlite3.connect(f'file:{self.run}/ledger.sqlite?mode=ro', uri=True, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            yield db
        finally:
            db.close()

    def safe_path(self, value):
        path = Path(value).resolve()
        if not any(path.is_relative_to(root) for root in (self.run, self.baseline, self.candidate)):
            raise ValueError('Image is outside the review catalog')
        return path

    def refresh(self):
        """Snapshot rejected products while workers keep their own ledger and locks."""
        with self.mutex:
            with self.ledger() as db:
                rows = list(db.execute("SELECT * FROM jobs WHERE state IN ('rejected','review_required') AND image_path IS NOT NULL ORDER BY updated DESC"))
                paths = {}
                for sql in ('SELECT image_sha256,path FROM references_to_review',
                            'SELECT image_sha256,image_path AS path FROM reference_repairs',
                            'SELECT image_sha256,image_path AS path FROM jobs WHERE image_path IS NOT NULL'):
                    for row in db.execute(sql):
                        if row['path'] and row['image_sha256']:
                            paths[row['image_sha256']] = row['path']
            wanted = {json.loads(row['request'])['sku'] for row in rows}
            wanted |= {json.loads(row['request']).get('reference', {}).get('sku') for row in rows
                       if json.loads(row['request']).get('reference')}
            products = {}
            for root in (self.baseline, self.candidate):
                for filename in ('1-simple.csv', '2-configurable.csv', '3-bundle.csv'):
                    path = root / 'data' / filename
                    if not path.exists():
                        continue
                    with path.open(newline='') as stream:
                        for row in csv.DictReader(stream):
                            if row.get('sku') in wanted:
                                products[row['sku']] = row
            imported = []
            for row in rows:
                job = json.loads(row['request'])
                design = job.get('design', {})
                review = json.loads(row['review']) if row['review'] else {}
                image = self.safe_path(row['image_path'])
                metadata = read_json(image.with_suffix('.json')) if image.with_suffix('.json').exists() else {}
                source_hash = metadata.get('reference_sha256') or review.get('reference_sha256')
                source_path = paths.get(source_hash)
                # Standalone repairs may use an earlier attempt, rather than a catalog source.
                if source_hash and not source_path:
                    for previous in image.parent.glob('attempt-*.json'):
                        info = read_json(previous)
                        if info.get('image_sha256') == source_hash:
                            source_path = str(previous.with_suffix('.jpg'))
                            break
                if source_path:
                    source_path = str(self.safe_path(source_path))
                product = products.get(job['sku'], {})
                ref = job.get('reference') or {}
                source_product = products.get(ref.get('sku'), {})
                item_id = f"{row['job_id']}-{row['image_sha256']}"
                item = {
                    'id': item_id, 'job_id': row['job_id'], 'image_sha256': row['image_sha256'],
                    'image_path': str(image), 'source_sha256': source_hash, 'source_path': source_path,
                    'group': source_hash or row['job_id'], 'sku': job['sku'],
                    'name': product.get('name') or design.get('subject') or job['sku'],
                    'department': job.get('department', ''), 'profile': job.get('profile', ''),
                    'material': design.get('material') or product.get('lab_spec_material', ''),
                    'color': design.get('color', ''), 'options': design.get('options', {}),
                    'description': plain(product.get('short_description')),
                    'dimensions': design.get('dimensions_cm', {}), 'price': product.get('price', ''),
                    'source_name': source_product.get('name') or (ref.get('sku') if ref else 'Standalone product'),
                    'source_label': 'Source product' if ref else 'Previous attempt',
                    'state': row['state'], 'attempt': row['attempts'],
                    'request': job, 'generation': metadata, 'automated_review': review,
                }
                imported.append((item_id, json.dumps(item, ensure_ascii=False), time.time()))
            with self.connect() as db:
                db.executemany('INSERT OR IGNORE INTO items VALUES(?,?,?)', imported)
            self.active = {item[0] for item in imported}
            return len(imported)

    def payload(self, item_id):
        with self.connect() as db:
            row = db.execute('SELECT payload FROM items WHERE id=?', (item_id,)).fetchone()
        if row is None:
            raise ValueError('Unknown review image')
        return json.loads(row['payload'])

    def listing(self):
        with self.mutex, self.connect() as db:
            rows = list(db.execute('SELECT i.payload,d.choice,d.note,d.revision,d.updated FROM items i LEFT JOIN decisions d ON d.item_id=i.id'))
            items = []
            for row in rows:
                item = json.loads(row['payload'])
                if item['id'] not in self.active and not row['choice']:
                    continue
                for key in ('request', 'generation', 'automated_review', 'image_path', 'source_path'):
                    item.pop(key)
                item['image_url'] = '/image/' + item['id'] + '/candidate'
                item['source_url'] = '/image/' + item['id'] + '/source' if json.loads(row['payload'])['source_path'] else None
                item['decision'] = {'choice': row['choice'], 'note': row['note'] or '',
                                    'revision': row['revision'] or 0, 'updated': row['updated']}
                item['active'] = item['id'] in self.active
                items.append(item)
            items.sort(key=lambda item: (item['department'], item['profile'], item['source_name'] or '', item['group'], item['sku']))
            return {'items': items, 'summary': self.summary(db)}

    def summary(self, db=None):
        if db is None:
            with self.connect() as connection:
                return self.summary(connection)
        counts = Counter()
        profiles = {}
        for row in db.execute('SELECT i.id,i.payload,d.choice,d.note FROM items i LEFT JOIN decisions d ON d.item_id=i.id'):
            if row['id'] not in self.active and not row['choice']:
                continue
            choice = row['choice'] or 'unreviewed'
            counts[choice] += 1
            item = json.loads(row['payload'])
            key = item['department'] + ' / ' + item['profile']
            profiles.setdefault(key, Counter())[choice] += 1
        return {'total': sum(counts.values()), **{key: counts[key] for key in ('unreviewed','keep','redo')},
                'profiles': {key: dict(value) for key, value in profiles.items()}}

    def save(self, body):
        item_id = body.get('id')
        choice = body.get('choice')
        note = body.get('note', '')
        revision = body.get('revision')
        if not isinstance(item_id, str) or 'choice' not in body:
            raise ValueError('An image and choice are required')
        if choice not in ('keep', 'redo', None) or not isinstance(note, str) or len(note) > 4000:
            raise ValueError('Invalid choice or note')
        if choice == 'redo' and not note.strip():
            raise ValueError('Add a note about what to redo')
        if type(revision) is not int or revision < 0:
            raise ValueError('A review revision is required')
        with self.mutex:
            item = self.payload(item_id)
            if choice is not None:
                with self.ledger() as ledger:
                    current = ledger.execute('SELECT * FROM jobs WHERE job_id=?', (item['job_id'],)).fetchone()
                if (current is None or current['image_sha256'] != item['image_sha256']
                        or current['state'] not in ('rejected', 'review_required')):
                    raise Conflict('This product changed during review. Refresh the queue.')
                if digest(self.safe_path(item['image_path'])) != item['image_sha256']:
                    raise Conflict('The displayed image changed. Refresh the queue.')
                if item['source_path'] and digest(self.safe_path(item['source_path'])) != item['source_sha256']:
                    raise Conflict('The source image changed. Refresh the queue.')
            with self.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                existing = db.execute('SELECT revision FROM decisions WHERE item_id=?', (item_id,)).fetchone()
                if (existing['revision'] if existing else 0) != revision:
                    raise Conflict('A newer choice is already saved. Refresh before changing it.')
                updated = time.time()
                result = {'choice': choice, 'note': note.strip() if choice else '',
                          'revision': revision + 1, 'updated': updated}
                db.execute('INSERT OR REPLACE INTO decisions VALUES(?,?,?,?,?)',
                           (item_id, result['choice'], result['note'], result['revision'], updated))
                db.execute('INSERT INTO events(item_id,choice,note,revision,created) VALUES(?,?,?,?,?)',
                           (item_id, result['choice'], result['note'], result['revision'], updated))
            self.export_feedback()
            return {'decision': result, 'summary': self.summary()}

    def feedback(self):
        with self.connect() as db:
            rows = list(db.execute('SELECT i.payload,d.choice,d.note,d.revision,d.updated FROM decisions d JOIN items i ON i.id=d.item_id WHERE d.choice IS NOT NULL ORDER BY d.updated'))
        return [{**json.loads(row['payload']), 'human_review': {
            'choice': row['choice'], 'note': row['note'], 'revision': row['revision'],
            'reviewed_at': datetime.fromtimestamp(row['updated'], timezone.utc).isoformat(),
            'reviewer': 'Matt', 'scope': 'image curation feedback'}} for row in rows]

    def export_feedback(self):
        path = self.output / 'feedback.jsonl'
        temporary = path.with_suffix('.jsonl.tmp')
        temporary.write_text(''.join(json.dumps(item, ensure_ascii=False) + '\n' for item in self.feedback()))
        temporary.replace(path)

    def image(self, item_id, kind):
        item = self.payload(item_id)
        key = 'image' if kind == 'candidate' else 'source' if kind == 'source' else None
        if key is None or not item.get(key + '_path'):
            raise ValueError('Image unavailable')
        path = self.safe_path(item[key + '_path'])
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != item[key + '_sha256']:
            raise Conflict('Image bytes changed')
        return content


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(fmt % args, flush=True)

    def send(self, status, content, kind='application/json; charset=utf-8'):
        if not isinstance(content, bytes):
            content = json.dumps(content, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.end_headers()
        self.wfile.write(content)

    def valid_host(self):
        return self.headers.get('Host') in self.server.hosts

    def do_GET(self):
        if not self.valid_host():
            return self.send(403, {'error': 'Local review only'})
        path = urlsplit(self.path).path
        try:
            if path == '/':
                content = Path(__file__).with_name('image_review_interface.html').read_text()
                return self.send(200, content.replace('__REVIEW_TOKEN__', self.server.token).encode(), 'text/html; charset=utf-8')
            if path == '/api/items':
                return self.send(200, self.server.store.listing())
            if path == '/api/feedback':
                data = ''.join(json.dumps(item, ensure_ascii=False) + '\n' for item in self.server.store.feedback())
                return self.send(200, data.encode(), 'application/x-ndjson; charset=utf-8')
            if path.startswith('/image/'):
                parts = path.split('/')
                if len(parts) == 4:
                    return self.send(200, self.server.store.image(parts[2], parts[3]), 'image/jpeg')
            return self.send(404, {'error': 'Not found'})
        except (ValueError, OSError) as exc:
            return self.send(409 if isinstance(exc, Conflict) else 404, {'error': str(exc)})

    def do_POST(self):
        if (not self.valid_host() or self.headers.get('Origin') not in self.server.origins
                or self.headers.get('X-Review-Token') != self.server.token):
            return self.send(403, {'error': 'Open the local review page before saving'})
        path = urlsplit(self.path).path
        try:
            length = int(self.headers.get('Content-Length', 0))
            if not 0 < length <= 12000:
                raise ValueError('Invalid request size')
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError('Invalid request')
            if path == '/api/decision':
                return self.send(200, self.server.store.save(body))
            if path == '/api/refresh':
                self.server.store.refresh()
                return self.send(200, self.server.store.listing())
            return self.send(404, {'error': 'Not found'})
        except (ValueError, OSError) as exc:
            return self.send(409 if isinstance(exc, Conflict) else 400, {'error': str(exc)})


def summarize_feedback(output):
    """Make a prompt/QA calibration report without opening or changing the worker ledger."""
    output = Path(output)
    with sqlite3.connect(f'file:{output}/feedback.sqlite?mode=ro', uri=True) as db:
        rows = list(db.execute('SELECT i.payload,d.choice,d.note,d.updated FROM decisions d JOIN items i ON i.id=d.item_id WHERE d.choice IS NOT NULL'))
    outcomes = Counter()
    cohorts = {key: {} for key in ('profile', 'material', 'color', 'lane')}
    notes = []
    kept_automated_rejections = 0
    for payload, choice, note, updated in rows:
        item = json.loads(payload)
        outcomes[choice] += 1
        values = {'profile': item['department'] + ' / ' + item['profile'],
                  'material': item['material'] or 'Unspecified', 'color': item['color'] or 'Unspecified',
                  'lane': item['request'].get('lane', 'Unspecified')}
        for key, value in values.items():
            cohorts[key].setdefault(value, Counter())[choice] += 1
        if choice == 'redo':
            notes.append({'sku': item['sku'], 'name': item['name'], 'profile': item['profile'],
                          'note': note, 'image_sha256': item['image_sha256'], 'source_sha256': item['source_sha256']})
        elif item['automated_review'].get('decision') in ('rejected', 'review_required'):
            kept_automated_rejections += 1
    report = {'snapshot_at': datetime.now(timezone.utc).isoformat(), 'outcomes': dict(outcomes),
              'cohorts': {key: {name: dict(count) for name, count in values.items()} for key, values in cohorts.items()},
              'human_keep_automated_hold': kept_automated_rejections, 'redo_notes': notes,
              'interpretation': 'Human curation feedback for a subsequent correction and QA calibration pass. Counts alone do not prove automated QA was wrong.'}
    path = output / 'feedback-summary.json'
    temporary = path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    temporary.replace(path)
    return report


def make_server(store, port=8877):
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.daemon_threads = True
    server.store = store
    server.token = secrets.token_urlsafe(32)
    actual_port = server.server_address[1]
    server.hosts = {f'127.0.0.1:{actual_port}', f'localhost:{actual_port}'}
    server.origins = {'http://' + host for host in server.hosts}
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True, type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--port', type=int, default=8877)
    parser.add_argument('--summarize', action='store_true', help='Write a feedback summary without starting a server')
    args = parser.parse_args()
    output = args.output or args.run.parent / 'human-image-review'
    if args.summarize:
        result = summarize_feedback(output)
        print(json.dumps({'snapshot_at': result['snapshot_at'], 'outcomes': result['outcomes'],
                          'summary': str(output / 'feedback-summary.json')}))
        return
    store = ReviewStore(args.run, output)
    server = make_server(store, args.port)
    url = f'http://127.0.0.1:{server.server_address[1]}/'
    print(f'Review interface: {url} ({len(store.active)} images)', flush=True)
    (output / 'server.json').write_text(json.dumps({'url': url, 'run': str(store.run), 'database': str(store.database), 'pid': os.getpid()}))
    (output / 'server.pid').write_text(str(os.getpid()))
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
