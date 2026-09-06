#!/usr/bin/env python3
"""Build the reproducible local database from the shipped attributed JSON records.

Run this only when deliberately editing the collection. The daily job reads the
database and never downloads new source material.
"""
import hashlib
import json
import os
import sqlite3
from collections import Counter
from pathlib import Path

from culture_library import ROOT, VERSION, ANCHOR, KINDS, validate_record, audit

FILES = {'illustration': 'art', 'poetry': 'poetry', 'text': 'text', 'quote': 'quote', 'music': 'music'}


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def origin(row):
    value = row.get('balance_origin') or row['creator_origin'].split(' · ')[0]
    lower = value.lower()
    # Match cultural labels as well as country adjectives, without changing credits.
    for prefix, group in [('japan','Japan'),('chin','China'),('india','India'),('iran','Iran'),
                          ('fran','France'),('french','France'),('german','Germany'),
                          ('ital','Italy'),('russia','Russia'),('brazil','Brazil'),
                          ('hungar','Hungary'),('greek','Greece'),('roman','Roman'),
                          ('english','England'),('england','England'),('scot','Scotland'),
                          ('american','United States'),('united states','United States')]:
        if lower.startswith(prefix):
            return group
    return value


def calendar(rows):
    """Every work used once; alternate creators/origins across and within days."""
    pools = {k: [r for r in rows if r['culture_type'] == k] for k in KINDS}
    if len(set(map(len, pools.values()))) != 1:
        raise ValueError('All five categories must have equal sizes for this calendar')
    previous = {}
    result = []
    days = len(pools[KINDS[0]])
    for slot in range(days):
        used_creators, used_origins = set(), set()
        for position, kind in enumerate(KINDS):
            last = previous.get(kind, {})
            chosen = min(pools[kind], key=lambda r: (
                r['creator'] in used_creators,
                origin(r) in used_origins,
                r['creator'] == last.get('creator'),
                origin(r) == (origin(last) if last else ''),
                digest(str(slot) + kind + r['key']),
            ))
            pools[kind].remove(chosen)
            used_creators.add(chosen['creator']); used_origins.add(origin(chosen))
            previous[kind] = chosen
            result.append((slot, position, kind, chosen['key']))
    return result, days


def build(root=ROOT):
    folder = root / 'data/culture'
    rows, hashes = [], {}
    for kind, name in FILES.items():
        path = folder / f'library-{name}.json'
        hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        batch = json.loads(path.read_text())
        if len(batch) < 366 or any(r['culture_type'] != kind for r in batch):
            raise ValueError('Need more than 365 correctly typed entries: ' + kind)
        rows.extend(batch)
    for row in rows:
        validate_record(row, root, check_image=True)
    if len({r['key'] for r in rows}) != len(rows):
        raise ValueError('Duplicate collection key')
    references = json.loads((folder / 'discoveries.json').read_text())
    schedule, cycle = calendar(rows)
    temporary = folder / 'library-building.sqlite'
    temporary.unlink(missing_ok=True)
    with sqlite3.connect(temporary) as db:
        db.executescript('''
          PRAGMA user_version=1;
          PRAGMA foreign_keys=ON;
          CREATE TABLE metadata(name TEXT PRIMARY KEY, value TEXT NOT NULL);
          CREATE TABLE works(key TEXT PRIMARY KEY, culture_type TEXT NOT NULL,
            creator TEXT NOT NULL, creator_origin TEXT NOT NULL, source_url TEXT NOT NULL,
            payload TEXT NOT NULL CHECK(json_valid(payload)));
          CREATE INDEX works_type ON works(culture_type);
          CREATE TABLE calendar(slot INTEGER NOT NULL, position INTEGER NOT NULL,
            culture_type TEXT NOT NULL, work_key TEXT NOT NULL UNIQUE REFERENCES works(key),
            PRIMARY KEY(slot,culture_type));
          CREATE TABLE discoveries(key TEXT PRIMARY KEY, payload TEXT NOT NULL CHECK(json_valid(payload)));
        ''')
        metadata = {'schema_version': VERSION, 'collection_version': '2026-09-06-v1',
                    'anchor': ANCHOR.isoformat(), 'timezone': 'Europe/Amsterdam', 'cycle_days': str(cycle),
                    'source_files_sha256': json.dumps(hashes, sort_keys=True)}
        db.executemany('INSERT INTO metadata VALUES(?,?)', metadata.items())
        db.executemany('INSERT INTO works VALUES(?,?,?,?,?,?)', [(r['key'], r['culture_type'], r['creator'], r['creator_origin'], r['source_url'], json.dumps(r, ensure_ascii=False, sort_keys=True)) for r in rows])
        db.executemany('INSERT INTO calendar VALUES(?,?,?,?)', schedule)
        db.executemany('INSERT INTO discoveries VALUES(?,?)', [(r['key'], json.dumps(r, ensure_ascii=False, sort_keys=True)) for r in references])
        db.commit()
        db.execute('VACUUM')
    os.replace(temporary, folder / 'library.sqlite')
    result = audit(root)
    result.update(database_sha256=hashlib.sha256((folder / 'library.sqlite').read_bytes()).hexdigest(),
                  source_files_sha256=hashes, discoveries=len(references),
                  creators=len({r['creator'] for r in rows}),
                  review_scope='Source metadata and content integrity checked automatically; sampled attribution review. Historical views belong to their sources.')
    (folder / 'library-manifest.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k:v for k,v in result.items() if k != 'source_files_sha256'}, ensure_ascii=False, indent=2))
    return result


if __name__ == '__main__':
    build()
