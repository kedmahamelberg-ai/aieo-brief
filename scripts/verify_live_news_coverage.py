#!/usr/bin/env python3
"""Compare the live Observatory edition with Brief data and rendered news cards."""
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from brief_contract import relationship_fingerprint, validate_complete_export
from source_chronology import public_event_ids
from validate_public_site import validate_home_news_coverage

ROOT = Path(__file__).resolve().parents[1]
OBSERVATORY = os.environ.get('OBSERVATORY_BASE_URL', 'https://observatory.hamelberg-ai.com').rstrip('/') + '/'
BRIEF = (os.environ.get('BRIEF_SITE_URL') or
         json.loads((ROOT / 'config/site.json').read_text()).get('site_url') or
         'https://brief.hamelberg-ai.com').rstrip('/') + '/'


def verify(observatory, brief, homepage):
    release, relationship = validate_complete_export(observatory)
    expected = public_event_ids(release)
    actual = [str(item.get('event_id') or '') for item in brief.get('stories') or []]
    if brief.get('release_id') != release['release_id'] or any(
        brief.get(key) != release[key] for key in ('period_start', 'period_end')
    ):
        raise ValueError(f"Live editions differ: Observatory {release['release_id']}, "
                         f"Brief {brief.get('release_id')}")
    if (brief.get('source_release_sha256') != release['content_sha256'] or
            brief.get('source_relationship_sha256') != relationship_fingerprint(relationship)):
        raise ValueError('Brief is not bound to the live Observatory source and classification release')
    if (brief.get('story_count') != len(actual) or len(actual) != len(set(actual)) or
            set(actual) != expected):
        raise ValueError(f'Observatory has {len(expected)} eligible developments, Brief data has '
                         f'{len(actual)} records; missing={sorted(expected-set(actual))[:5]}, '
                         f'extra={sorted(set(actual)-expected)[:5]}')
    coverage = validate_home_news_coverage(brief, homepage)
    missing = [item['event_id'] for item in brief.get('stories') or []
               if item.get('evidence_complete') is True and not item.get('has_editorial')]
    if missing:
        raise ValueError(f'{len(missing)} source-ready developments still lack a completed Brief article; '
                         f'headline cards do not complete publication. First IDs: {missing[:5]}')
    return {'release_id': release['release_id'], 'period_start': release['period_start'],
            'period_end': release['period_end'], 'observatory_developments': len(expected),
            'brief_records': len(actual), **coverage}


def get(session, url):
    response = session.get(url, params={'coverage_check': int(time.time())},
                           headers={'Cache-Control': 'no-cache'}, timeout=(10, 30))
    response.raise_for_status()
    return response


def verify_story_page(story, html):
    """A complete data record must have the same prose and sources on its route."""
    key = story['event_id']
    if not story.get('what_happened') or not story.get('body_paragraphs'):
        raise ValueError(f'Completed news record {key} has no article body')
    soup = BeautifulSoup(html, 'html.parser')
    if any(str(meta.get('http-equiv', '')).lower() == 'refresh'
           for meta in soup.find_all('meta')):
        raise ValueError(f'Live article {key} redirects instead of displaying the article')
    for node in soup(['script', 'style', 'noscript']):
        node.decompose()
    visible = ' '.join(soup.get_text(' ', strip=True).split())
    fields = {field: story.get(field) for field in
              ('headline', 'deck', 'what_happened', 'why_it_matters',
               'for_humans', 'for_ai', 'limitation')}
    fields.update({f'body_paragraphs[{i}]': value
                   for i, value in enumerate(story['body_paragraphs'])})
    for field, value in fields.items():
        if value and ' '.join(str(value).split()) not in visible:
            raise ValueError(f'Live article {key} is missing its saved {field}')
    links = {anchor.get('href') for anchor in soup.find_all('a', href=True)}
    for source in story.get('sources') or []:
        if source.get('url') not in links:
            raise ValueError(f'Live article {key} is missing its saved source URL')


def verify_article_routes(brief):
    stories = [story for story in (brief.get('stories') or []) + (brief.get('recent_news') or [])
               if story.get('has_editorial')]
    def check(story):
        try:
            url = urljoin(BRIEF, story['path'].removesuffix('index.html'))
            if urlparse(url).netloc != urlparse(BRIEF).netloc:
                raise ValueError('News route leaves the Brief')
            with requests.Session() as session:
                # Check the ordinary reader URL: a cache-busting request can
                # conceal a stale or missing article served to actual readers.
                page = session.get(url, timeout=(10, 30))
                page.raise_for_status()
            if urlparse(page.url).netloc != urlparse(BRIEF).netloc:
                raise ValueError('News route redirects outside the Brief')
            verify_story_page(story, page.text)
        except (ValueError, KeyError, requests.RequestException) as exc:
            return f'{story.get("event_id", "unknown")}: {exc}'
    with ThreadPoolExecutor(max_workers=5) as pool:
        failures = [failure for failure in pool.map(check, stories) if failure]
    if failures:
        raise ValueError(f'{len(failures)} of {len(stories)} live news article routes failed:\n'
                         + '\n'.join(failures))
    return len(stories)


def main():
    error = None
    for attempt in range(3):
        try:
            with requests.Session() as session:
                observatory = get(session, urljoin(OBSERVATORY, 'data/brief/current.json')).json()
                brief = get(session, urljoin(BRIEF, 'data/current.json')).json()
                homepage = get(session, BRIEF).text
            report = verify(observatory, brief, homepage)
            report['live_article_routes_verified'] = verify_article_routes(brief)
            report['checked_at'] = datetime.now(timezone.utc).isoformat()
            print(json.dumps(report, indent=2))
            if os.environ.get('GITHUB_STEP_SUMMARY'):
                with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as summary:
                    summary.write(f"Live news coverage: {report['observatory_developments']} Observatory "
                                  f"developments, {report['brief_records']} Brief records, "
                                  f"{report['rendered_news_cards']} homepage cards, "
                                  f"{report['full_brief_articles']} full Brief articles; "
                                  f"{report['live_article_routes_verified']} current and retained live bodies "
                                  f"and source links verified.\n")
            return
        except (ValueError, KeyError, requests.RequestException) as exc:
            error = exc
            if attempt < 2:
                time.sleep(10)
    print(f'::error::Live Observatory–Brief news coverage mismatch: {error}')
    raise SystemExit(1)


if __name__ == '__main__':
    main()
