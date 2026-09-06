"""A local, attributed cultural collection. Daily selection makes no HTTP calls."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import Counter
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlsplit

from daily_selection import reading_day

ROOT = Path(__file__).resolve().parents[1]
KINDS = ('illustration', 'poetry', 'text', 'quote', 'music')
ANCHOR = date(2026, 9, 6)
VERSION = 'aieo_culture_library_v1'


def https(value):
    p = urlsplit(str(value or ''))
    return p.scheme == 'https' and bool(p.hostname) and not p.username and not p.password


def validate_record(row, root=None, check_image=False):
    if not re.fullmatch(r'culture:[a-f0-9]{24}', row.get('key', '')):
        raise ValueError('Invalid culture key')
    if row.get('culture_type') not in KINDS:
        raise ValueError('Unknown culture type')
    required = ('headline', 'creator', 'creator_origin', 'publisher', 'work_date', 'provenance_id', 'source_checked_on')
    if any(not row.get(k) for k in required):
        raise ValueError('Incomplete culture attribution: ' + row['key'])
    rights = row.get('rights') or {}
    if not https(row.get('source_url')) or not rights.get('label') or not https(rights.get('url')):
        raise ValueError('Missing source or reuse terms: ' + row['key'])
    kind = row['culture_type']
    if kind == 'illustration':
        path = row.get('image_path', '')
        if not re.fullmatch(r'assets/culture/[a-f0-9]{24}\.jpg', path):
            raise ValueError('Invalid cached art path')
        if check_image:
            image = (root or ROOT) / path
            if not image.is_file() or not image.read_bytes().startswith(b'\xff\xd8\xff'):
                raise ValueError('Missing museum image: ' + path)
    elif kind == 'music':
        if not https(row.get('media_url')) or not 45 <= row.get('duration_seconds', 0) <= 1200:
            raise ValueError('Missing music recording')
        label = rights['label']
        if not (label.startswith(('CC BY ', 'CC BY-SA ', 'CC0', 'Public domain')) and not re.search(r'\b(?:NC|ND)\b', label)):
            raise ValueError('Recording does not have compatible source-declared terms')
        if not row.get('recording_credit'):
            raise ValueError('Recording credit is missing')
    else:
        if not row.get('excerpt') or not row.get('source_locator'):
            raise ValueError('Text or its location is missing')
        if kind == 'quote' and row['excerpt'] not in row.get('quote_context', ''):
            raise ValueError('Quotation does not occur in its surrounding passage')
        if kind == 'poetry' and row['excerpt'] != '\n'.join(row.get('poem_lines', [])):
            raise ValueError('Poem line breaks changed')


def connect(root=None):
    path = (root or ROOT) / 'data/culture/library.sqlite'
    if not path.is_file():
        raise ValueError('The stored culture database is missing. Install the complete update.')
    return sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)


def summary(root=None):
    with closing(connect(root)) as db:
        meta = dict(db.execute('SELECT name, value FROM metadata'))
        counts = dict(db.execute('SELECT culture_type, COUNT(*) FROM works GROUP BY culture_type'))
        if meta.get('schema_version') != VERSION or set(counts) != set(KINDS) or min(counts.values()) < 366:
            raise ValueError('The stored collection needs at least 366 records of each type')
        return {**meta, 'counts': counts, 'total': sum(counts.values()), 'cycle_days': int(meta['cycle_days'])}


def select(day=None, root=None):
    day = date.fromisoformat(day) if isinstance(day, str) else day or reading_day()
    info = summary(root)
    offset = (day - date.fromisoformat(info['anchor'])).days % info['cycle_days']
    with closing(connect(root)) as db:
        rows = [json.loads(p) for p, in db.execute(
            'SELECT w.payload FROM calendar c JOIN works w ON w.key=c.work_key WHERE c.slot=? ORDER BY c.position', (offset,))]
    if Counter(r['culture_type'] for r in rows) != Counter(KINDS):
        raise ValueError('A daily selection must contain one work of each type')
    for row in rows:
        validate_record(row, root, check_image=True)
        row.update(date=day.isoformat(), selected_on=day.isoformat(), library_version=info['collection_version'])
    return rows


def publication(day=None, root=None):
    """Construct today's selection in memory; preserve recent published selections."""
    root = root or ROOT
    day = date.fromisoformat(day) if isinstance(day, str) else day or reading_day()
    settings = json.loads((root / 'config/culture.json').read_text())
    if not settings.get('enabled', True):
        return {'schema_version': 'aieo_culture_public_v2', 'items': [], 'editions': {}}
    target = root / 'data/culture/current.json'
    old = json.loads(target.read_text()) if target.exists() else {}
    cutoff = (day - timedelta(days=int(settings.get('retention_days', 45)))).isoformat()
    # Never pretend a selection happened on a day when no build was made.
    records = {r['key']: r for r in old.get('items', []) if cutoff <= r.get('date', '') < day.isoformat()}
    today = select(day, root)
    for row in today:
        records[row['key']] = row
    items = sorted(records.values(), key=lambda r: (r['date'], r['key']), reverse=True)
    editions = {}
    for row in items:
        editions.setdefault(row['date'], []).append(row['key'])
    return {'schema_version': 'aieo_culture_public_v2', 'selection_method': 'stored_calendar',
            'selection_timezone': 'Europe/Amsterdam', 'latest_selection': day.isoformat(),
            'items': items, 'editions': editions}


def discoveries(day=None, root=None):
    """Author / museum references: links, without copying protected works."""
    day = date.fromisoformat(day) if isinstance(day, str) else day or reading_day()
    with closing(connect(root)) as db:
        rows = [json.loads(p) for p, in db.execute('SELECT payload FROM discoveries ORDER BY key')]
    if not rows:
        return []
    offset = (day - ANCHOR).days % len(rows)
    return rows[offset:] + rows[:offset]


def audit(root=None):
    root = root or ROOT
    info = summary(root)
    for name, expected in json.loads(info['source_files_sha256']).items():
        if not re.fullmatch(r'library-(?:art|music|poetry|text|quote)\.json',name):
            raise ValueError('Invalid culture source file')
        if hashlib.sha256((root/'data/culture'/name).read_bytes()).hexdigest() != expected:
            raise ValueError('The collection data changed. Rebuild the culture database: ' + name)
    with closing(connect(root)) as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Culture database failed its integrity check')
        rows = [json.loads(p) for p, in db.execute('SELECT payload FROM works')]
        schedule = db.execute('SELECT slot, culture_type, work_key FROM calendar').fetchall()
    fingerprints = set()
    for row in rows:
        validate_record(row, root, check_image=True)
        fingerprint = (row['culture_type'], row.get('content_fingerprint', row['provenance_id']))
        if fingerprint in fingerprints:
            raise ValueError('Duplicate work in a category')
        fingerprints.add(fingerprint)
    if len(schedule) != 5 * info['cycle_days']:
        raise ValueError('Calendar is incomplete')
    if len({key for _, _, key in schedule}) != len(schedule):
        raise ValueError('The calendar repeats a work inside its first cycle')
    return {**info, 'result': 'passed', 'cached_images': info['counts']['illustration'],
            'daily_selection_network_calls': 0}
