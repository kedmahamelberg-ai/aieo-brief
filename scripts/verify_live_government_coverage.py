#!/usr/bin/env python3
"""Check that every eligible Monitor government record reached the live Brief."""
from __future__ import annotations

import json
import os
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

from government_briefs import FEED, POLICY, candidate, clean, fingerprint, monitor_record, page_headline

ROOT = Path(__file__).resolve().parents[1]
BRIEF = (os.environ.get('BRIEF_SITE_URL') or
         json.loads((ROOT / 'config/site.json').read_text()).get('site_url') or
         'https://brief.hamelberg-ai.com').rstrip('/') + '/'
MAX_SNAPSHOT_BYTES = 25_000_000
HELD_ISSUE_TITLE = 'Government AI labels held for source review'


class GovernmentCards(HTMLParser):
    def __init__(self):
        super().__init__()
        self.cards = []
        self.sync = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == 'p' and attributes.get('id') == 'government-sync':
            self.sync = attributes
        if tag != 'article':
            return
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
    if state.get('monitor_as_of') != snapshot['as_of']:
        raise ValueError('Brief government import has not checked the latest Monitor snapshot')
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
        canonical = monitor_record(item, checked[ident])
        for field, value in canonical.items():
            if record.get(field) != value:
                raise ValueError(f'Saved Brief record {ident} does not mechanically reuse Monitor {field}')
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
                                          ('headline', 'headline'), ('deck', 'summary'),
                                          ('body_paragraphs', 'body_paragraphs')):
            if item.get(public_field) != record.get(saved_field):
                raise ValueError(f"Live Brief {item['id']} has stale {public_field}")
        if item.get('announcement_paragraphs') != (record['body_paragraphs'] or [record['summary']]):
            raise ValueError(f"Live Brief {item['id']} has stale announcement paragraphs")
        if item.get('page_headline') != page_headline(record):
            raise ValueError(f"Live Brief {item['id']} has a stale full headline")
    parser = GovernmentCards()
    parser.feed(html)
    if not parser.sync or parser.sync.get('data-monitor-as-of') != state['monitor_as_of'] or parser.sync.get('data-last-checked') != state.get('last_checked_at'):
        raise ValueError('Live Governments say page does not show the saved Monitor check time')
    card_keys = {item['key']: item['date'] for item in governments}
    same_ids('Live Governments say cards', [key for key, _ in parser.cards], card_keys)
    for key, day in parser.cards:
        if day != card_keys[key]:
            raise ValueError(f'Live Governments say card {key} has a stale date')
    held = [item for item in snapshot['items']
            if 'artificial_intelligence' in (item.get('topics') or [])
            and item.get('classification_status') == 'needs_review']
    return {'monitor_as_of': snapshot['as_of'], 'monitor_eligible': len(expected),
            'brief_saved': len(records), 'brief_live_data': len(governments),
            'brief_live_cards': len(parser.cards),
            'monitor_ai_held_for_review': len(held),
            'held_ids': [str(item['id']) for item in held],
            'external_benchmarks': {code: sum(item.get('country_code') == code for item in expected.values())
                                    for code in ('US', 'CA', 'CN')}}


def verify_article_page(item, record, html):
    """Require the actual article's copy and source, not just a matching card."""
    soup = BeautifulSoup(html, 'html.parser')
    if any(str(meta.get('http-equiv', '')).lower() == 'refresh'
           for meta in soup.find_all('meta')):
        raise ValueError(f"Live government article {item['id']} redirects instead of showing its body")
    article = soup.select_one('#article-content')
    if article is None:
        raise ValueError(f"Live government article {item['id']} has no article content")
    section = article.select_one('section[aria-labelledby="announcement"]')
    paragraphs = [clean(p.get_text(' ', strip=True)) for p in section.find_all('p')] if section else []
    expected = record['body_paragraphs'] or [record['summary']]
    if paragraphs != expected:
        raise ValueError(f"Live government article {item['id']} has stale or missing Monitor body")
    heading = article.find('h1')
    if heading is None or page_headline(record) != clean(heading.get_text(' ', strip=True)):
        raise ValueError(f"Live government article {item['id']} has a stale headline")
    if not article.find('time', attrs={'datetime': record['date']}):
        raise ValueError(f"Live government article {item['id']} has a stale date")
    kicker = article.select_one('.story-kicker')
    if kicker is None or record['country'] not in clean(kicker.get_text(' ', strip=True)):
        raise ValueError(f"Live government article {item['id']} has a stale country")
    source_links = {a.get('href') for a in article.select('a[data-source-link]')}
    if source_links != {record['url']}:
        raise ValueError(f"Live government article {item['id']} has a stale source link")


def verify_article_routes(state, public):
    def check(item):
        try:
            url = urljoin(BRIEF, item['path'].removesuffix('index.html'))
            if urlsplit(url).netloc != urlsplit(BRIEF).netloc:
                raise ValueError('Government article route leaves the Brief')
            # Use the ordinary reader URL: a cache bypass can hide stale pages.
            page = requests.get(url, timeout=(10, 30), allow_redirects=False)
            page.raise_for_status()
            if 300 <= page.status_code < 400:
                raise ValueError('Government article redirects instead of showing its body')
            if urlsplit(page.url).netloc != urlsplit(BRIEF).netloc:
                raise ValueError('Government article redirects outside the Brief')
            verify_article_page(item, state['records'][item['id']], page.text)
        except (ValueError, KeyError, requests.RequestException) as exc:
            return f"{item.get('id', 'unknown')}: {exc}"
    items = public.get('governments') or []
    with ThreadPoolExecutor(max_workers=5) as pool:
        failures = [failure for failure in pool.map(check, items) if failure]
    if failures:
        raise ValueError(f'{len(failures)} of {len(items)} live government articles failed:\n'
                         + '\n'.join(failures))
    return len(items)


def get(session, url, *, max_bytes=None):
    response = session.get(url, params={'coverage_check': int(time.time())},
                           headers={'Cache-Control': 'no-cache'}, timeout=(10, 45))
    response.raise_for_status()
    if max_bytes and len(response.content) > max_bytes:
        raise ValueError('Monitor government snapshot exceeds 25 MB')
    return response


def sync_held_issue(snapshot):
    """Keep one GitHub issue for unpublished AI labels; unchanged holds are quiet."""
    token, repo = os.environ.get('GITHUB_TOKEN'), os.environ.get('GITHUB_REPOSITORY')
    if not token or not repo:
        return
    held = sorted((item for item in snapshot['items']
                   if 'artificial_intelligence' in (item.get('topics') or [])
                   and item.get('classification_status') == 'needs_review'),
                  key=lambda item: str(item.get('id') or ''))
    base = f'https://api.github.com/repos/{repo}/issues'
    with requests.Session() as session:
        session.headers.update({'Authorization': f'Bearer {token}',
                                'Accept': 'application/vnd.github+json'})
        issue = None
        for page in range(1, 11):
            response = session.get(base, params={'state': 'open', 'per_page': 100, 'page': page}, timeout=20)
            response.raise_for_status()
            rows = response.json()
            issue = next((row for row in rows if row.get('title') == HELD_ISSUE_TITLE
                          and 'pull_request' not in row), None)
            if issue or len(rows) < 100:
                break
        if not held:
            if issue:
                response = session.patch(issue['url'], json={'state': 'closed', 'state_reason': 'completed'}, timeout=20)
                response.raise_for_status()
            return
        lines = ['These Monitor records carry an AI label but remain unpublished because Monitor marked them `needs_review`.',
                 'Review each complete original source before changing its label or published copy. The Brief must not make a second AI judgment.', '']
        for item in held:
            lines.append(f"- `{item['id']}` · {item.get('country_code', '?')} · {item.get('published_date') or str(item.get('published_at') or '')[:10]} · {item.get('url', '')}")
        body = '\n'.join(lines) + '\n'
        if issue:
            if issue.get('body') != body:
                response = session.patch(issue['url'], json={'body': body}, timeout=20)
                response.raise_for_status()
        else:
            response = session.post(base, json={'title': HELD_ISSUE_TITLE, 'body': body}, timeout=20)
            response.raise_for_status()


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
            sync_held_issue(snapshot)
            if report['monitor_ai_held_for_review']:
                print(f"::warning::{report['monitor_ai_held_for_review']} AI-labelled Monitor announcements are held for source review and correctly absent from the Brief; IDs: {', '.join(report['held_ids'])}")
            report['live_article_routes_verified'] = verify_article_routes(state, public)
            report['checked_at'] = datetime.now(timezone.utc).isoformat()
            print(json.dumps(report, indent=2))
            if os.environ.get('GITHUB_STEP_SUMMARY'):
                with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as summary:
                    summary.write(f"Government coverage: {report['monitor_eligible']} Monitor eligible, "
                                  f"{report['brief_saved']} Brief saved, {report['brief_live_data']} Brief data, "
                                  f"{report['brief_live_cards']} live cards; "
                                  f"{report['live_article_routes_verified']} article bodies and sources verified; "
                                  f"{report['monitor_ai_held_for_review']} AI-labelled Monitor items held for source review.\n")
            return
        except (ValueError, KeyError, TypeError, requests.RequestException) as exc:
            error = exc
            if attempt < 4:
                time.sleep(15)
    print(f'::error::Monitor–Brief government coverage mismatch: {error}')
    raise SystemExit(1)


if __name__ == '__main__':
    main()
