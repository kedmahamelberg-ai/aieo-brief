#!/usr/bin/env python3
"""Check that every eligible Monitor government record reached the live Brief."""
from __future__ import annotations

import json
import os
import time
from collections import Counter
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

import requests

from government_briefs import FEED, POLICY, candidate, fingerprint

ROOT = Path(__file__).resolve().parents[1]
BRIEF = (os.environ.get('BRIEF_SITE_URL') or
         json.loads((ROOT / 'config/site.json').read_text()).get('site_url') or
         'https://brief.hamelberg-ai.com').rstrip('/') + '/'
MAX_SNAPSHOT_BYTES = 25_000_000


class GovernmentCards(HTMLParser):
    def __init__(self):
        super().__init__()
        self.cards = []

    def handle_starttag(self, tag, attrs):
        if tag != 'article':
            return
        attributes = dict(attrs)
        if 'government-card' in attributes.get('class', '').split():
            self.cards.append((attributes.get('data-key'), attributes.get('data-date')))


def same_ids(label, actual, expected):
    counts = Counter(actual)
    if set(actual) != set(expected) or any(count != 1 for count in counts.values()):
        raise ValueError(f'{label}: expected {len(expected)}, found {len(actual)}; '
                         f'missing={sorted(set(expected)-set(actual))[:8]}, '
                         f'extra={sorted(set(actual)-set(expected))[:8]}, '
                         f'duplicates={sorted(key for key, count in counts.items() if count > 1)[:8]}')


def verify(snapshot, state, public, html):
    if not isinstance(snapshot, dict) or not snapshot.get('as_of') or not isinstance(snapshot.get('items'), list):
        raise ValueError('Monitor government snapshot is invalid')
    if state.get('policy') != POLICY:
        raise ValueError('Saved Brief government import policy is stale')
    expected = {}
    for item in snapshot['items']:
        ident = str(item.get('id') or '')
        if ident and ident not in expected and candidate(item):
            expected[ident] = item
    records = state.get('records') or {}
    checked = state.get('checked') or {}
    same_ids('Saved Brief government IDs', list(records), expected)
    same_ids('Saved Brief input fingerprints', list(checked), expected)
    for ident, item in expected.items():
        record = records[ident]
        if checked[ident] != fingerprint(item) or record.get('input_fingerprint') != checked[ident]:
            raise ValueError(f'Saved Brief record {ident} does not match its current Monitor input')
        if (record.get('date') != (item.get('published_date') or str(item.get('published_at') or '')[:10]) or
                any(record.get(field) != item.get(field) for field in ('country', 'country_code', 'url'))):
            raise ValueError(f'Saved Brief record {ident} has mismatched source, country or date')
    governments = public.get('governments') or []
    if public.get('government_count') != len(governments):
        raise ValueError('Brief public government_count does not match its records')
    same_ids('Live Brief government IDs', [str(item.get('id') or '') for item in governments], expected)
    for item in governments:
        record = records[item['id']]
        for public_field, saved_field in (('date', 'date'), ('country_code', 'country_code'),
                                          ('country', 'country'), ('url', 'url'),
                                          ('headline', 'headline'), ('deck', 'summary')):
            if item.get(public_field) != record.get(saved_field):
                raise ValueError(f"Live Brief {item['id']} has stale {public_field}")
    parser = GovernmentCards()
    parser.feed(html)
    card_keys = {item['key']: item['date'] for item in governments}
    same_ids('Live Governments say cards', [key for key, _ in parser.cards], card_keys)
    for key, day in parser.cards:
        if day != card_keys[key]:
            raise ValueError(f'Live Governments say card {key} has a stale date')
    return {'monitor_as_of': snapshot['as_of'], 'monitor_eligible': len(expected),
            'brief_saved': len(records), 'brief_live_data': len(governments),
            'brief_live_cards': len(parser.cards),
            'external_benchmarks': {code: sum(item.get('country_code') == code for item in expected.values())
                                    for code in ('US', 'CA', 'CN')}}


def get(session, url, *, max_bytes=None):
    response = session.get(url, params={'coverage_check': int(time.time())},
                           headers={'Cache-Control': 'no-cache'}, timeout=(10, 45))
    response.raise_for_status()
    if max_bytes and len(response.content) > max_bytes:
        raise ValueError('Monitor government snapshot exceeds 25 MB')
    return response


def main():
    error = None
    for attempt in range(5):
        try:
            state = json.loads((ROOT / 'data/governments/public.json').read_text())
            with requests.Session() as session:
                snapshot = get(session, FEED, max_bytes=MAX_SNAPSHOT_BYTES).json()
                public = get(session, urljoin(BRIEF, 'data/current.json')).json()
                html = get(session, urljoin(BRIEF, 'governments-say/')).text
            report = verify(snapshot, state, public, html)
            report['checked_at'] = datetime.now(timezone.utc).isoformat()
            print(json.dumps(report, indent=2))
            if os.environ.get('GITHUB_STEP_SUMMARY'):
                with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as summary:
                    summary.write(f"Government coverage: {report['monitor_eligible']} Monitor eligible, "
                                  f"{report['brief_saved']} Brief saved, {report['brief_live_data']} Brief data, "
                                  f"{report['brief_live_cards']} live cards.\n")
            return
        except (ValueError, KeyError, TypeError, requests.RequestException) as exc:
            error = exc
            if attempt < 4:
                time.sleep(15)
    print(f'::error::Monitor–Brief government coverage mismatch: {error}')
    raise SystemExit(1)


if __name__ == '__main__':
    main()
