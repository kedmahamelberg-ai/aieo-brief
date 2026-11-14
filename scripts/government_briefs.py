"""Publish the Monitor's AI-labelled government narratives in The Brief."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
import requests

ROOT = Path(__file__).resolve().parents[1]
FEED = 'https://monitor.hamelberg-ai.com/government-data.json'
POLICY = 'government-ai-brief-v3'
PREVIOUS_POLICY = 'government-ai-brief-v2'


def clean(value):
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def published_day(item):
    # The publisher's local publication date takes precedence over UTC midnight.
    value = item.get('published_date') or str(item.get('published_at') or '')[:10]
    try:
        return date.fromisoformat(value).isoformat()
    except (ValueError, TypeError):
        return ''


def candidate(item):
    """The Monitor's AI topic label is the sole editorial inclusion decision."""
    url = urlsplit(str(item.get('url') or ''))
    topics = item.get('topics')
    return bool(item.get('id') and published_day(item) and item.get('country')
                and re.fullmatch(r'[A-Z]{2}', str(item.get('country_code', '')))
                and url.scheme == 'https' and url.hostname and not url.username
                and item.get('translation_complete') is True
                and item.get('classification_status') in ('provisional', 'human_reviewed')
                and isinstance(topics, list) and 'artificial_intelligence' in topics
                and clean(item.get('english_summary')))


def fingerprint(item, policy=POLICY):
    fields = {k: item.get(k) for k in ('id', 'country', 'country_code', 'url', 'english_summary')}
    fields['date'] = published_day(item)
    if policy == POLICY:
        fields['ticker_message'] = item.get('ticker_message')
        fields['topics'] = item.get('topics')
    return hashlib.sha256(json.dumps([policy, fields], sort_keys=True).encode()).hexdigest()


def monitor_record(item, sha):
    """Reuse the Monitor's own English wording and official source link."""
    summary = clean(item['english_summary'])
    headline = clean(item.get('ticker_message')) or re.split(r'(?<=[.!?])\s+', summary, maxsplit=1)[0]
    return {'id': str(item['id']), 'country': clean(item['country']),
            'country_code': item['country_code'], 'url': item['url'],
            'date': published_day(item), 'headline': headline,
            'summary': summary, 'body_paragraphs': [], 'input_fingerprint': sha}


def refresh(snapshot, state):
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get('items'), list) or not snapshot.get('as_of'):
        raise ValueError('Monitor government snapshot is invalid')
    records = dict(state.get('records', {}))
    checked = dict(state.get('checked', {}))
    seen = set()
    for item in snapshot['items']:
        ident = str(item.get('id') or '')
        if ident in seen:
            continue
        seen.add(ident)
        if not candidate(item):
            records.pop(ident, None)
            checked.pop(ident, None)
            continue
        sha = fingerprint(item)
        if checked.get(ident) == sha:
            continue
        # Preserve previously published copy and community identity when its
        # source evidence has not changed. An old exclusion is reconsidered.
        if ident in records and checked.get(ident) == fingerprint(item, PREVIOUS_POLICY):
            records[ident] = {**records[ident], 'input_fingerprint': sha}
        else:
            records[ident] = monitor_record(item, sha)
        checked[ident] = sha
    return {'policy': POLICY, 'monitor_as_of': snapshot['as_of'],
            'last_checked_at': datetime.now(timezone.utc).isoformat(),
            'records': records, 'checked': checked,
            'retry': {}, 'pending': 0, 'failures': []}


def load(root=ROOT):
    path = Path(root) / 'data/governments/public.json'
    return json.loads(path.read_text()) if path.exists() else {'records': {}}


def cards(root=ROOT):
    result = []
    photos = json.loads((Path(root) / 'config/story-photos.json').read_text())['photos']
    for row in load(root).get('records', {}).values():
        # A UUID5 gives these articles stable community identities without new
        # database key types. It never references an Observatory event record.
        key = 'event:' + str(uuid.uuid5(uuid.NAMESPACE_URL, FEED + '#' + row['id']))
        ident = key.removeprefix('event:')
        photo = photos.get({'FR': 'fr', 'US': 'us'}.get(row['country_code'], ''))
        # Occasional country context, never a purported photo of the event.
        if photo and (int(hashlib.sha256(row['id'].encode()).hexdigest()[:2], 16) % 2 == 1):
            photo = {**photo, 'caption': row['country'] + ' · Archive image for country context; not this announcement.'}
        else:
            photo = None
        result.append({**row, 'key': key, 'kind': 'news', 'section': 'governments',
                       'slug': 'government-' + ident, 'path': 'story/government-' + ident + '/index.html',
                       'deck': row['summary'], 'publisher': 'Government of ' + row['country'],
                       'source_count': 1, 'sources': [{'publisher': 'Government of ' + row['country'],
                           'headline': 'Official government announcement', 'url': row['url'], 'date': row['date'], 'language': ''}],
                       'display_date': date.fromisoformat(row['date']).strftime('%-d %b %Y'), 'markets': [],
                       'market_label': row['country'], 'topic': 'policy', 'topic_label': 'Government & AI',
                       'human_direction': 'none', 'ai_direction': 'none', 'human_label': 'No direction stated',
                       'ai_label': 'No direction stated', 'for_humans': '', 'for_ai': '',
                       'has_editorial': True, 'evidence_complete': False, 'body_paragraphs': row.get('body_paragraphs', []),
                       'summary_basis': 'Monitor government narrative · AI topic label', 'reading_minutes': 1,
                       'edition': 'Governments · ' + row['date'][:7], 'publication_language': 'en',
                       'english_status': 'checked', 'government_photo': photo})
    return sorted(result, key=lambda x: (x['date'], x['country'], x['key']), reverse=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    response = requests.get(FEED, timeout=45)
    response.raise_for_status()
    snapshot = response.json()
    previous = load()
    if args.dry_run:
        if not isinstance(snapshot.get('items'), list) or not snapshot.get('as_of'):
            raise ValueError('Monitor government snapshot is invalid')
        pending = sum(candidate(item) and previous.get('checked', {}).get(str(item['id'])) != fingerprint(item)
                      for item in snapshot['items'])
        print('AI-labelled Monitor narratives awaiting import:', pending)
        return 0
    state = refresh(snapshot, previous)
    path = ROOT / 'data/governments/public.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)
    print(json.dumps({'policy': state['policy'], 'monitor_as_of': state['monitor_as_of'],
                      'last_checked_at': state['last_checked_at'],
                      'retained': len(state['records']), 'pending': 0, 'failures': []}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
