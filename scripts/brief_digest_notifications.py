#!/usr/bin/env python3
"""Twice-daily opt-in Web Push, using only already-published Brief content.

No API model calls, no emails, and no automatic migration of weekly consent.
The database owns the delivery window and atomic per-device/per-slot claims.
"""
import argparse
import json
import re
import time
from datetime import datetime, time as clock, timezone
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from zoneinfo import ZoneInfo

import requests
from brief_contract import load_config, safe_url
from news_notifications import client, ENDPOINT, PushSession

AMSTERDAM = ZoneInfo('Europe/Amsterdam')
KEY = re.compile(r'(?:event:[0-9a-f-]{36}|(?:paper|culture):[0-9a-f]{24})\Z', re.I)
TOPICS = {'news': 'AI newspaper', 'culture': 'Culture', 'research': 'AI research'}
ROOT = Path(__file__).resolve().parents[1]


def due_slot(now=None):
    """DST-safe mirror of the database window; database checks again on claim."""
    local = (now or datetime.now(timezone.utc)).astimezone(AMSTERDAM)
    current = local.time().replace(tzinfo=None)
    suffix = 'am' if clock(8, 30) <= current < clock(12) else 'pm' if clock(18, 30) <= current < clock(22) else None
    return local.strftime('%Y-%m-%d-') + suffix if suffix else None


def selection(published, topics, slot):
    """One published item per selected category, with deterministic rotation.

    News/research with no original summary are not used to invite a reader to
    an empty brief. Culture rotates within the latest available day's set.
    """
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}-(am|pm)', slot):
        raise ValueError('Invalid notification slot')
    day = datetime.fromisoformat(slot[:10]).date()
    selected = []
    for topic, field in [('news', 'stories'), ('culture', 'culture'), ('research', 'research')]:
        if topic not in topics:
            continue
        pool = [item for item in published.get(field, [])
                if item.get('kind') == topic and KEY.fullmatch(item.get('key', ''))
                and re.fullmatch(r'\d{4}-\d{2}-\d{2}', item.get('date', ''))
                and item['date'] <= day.isoformat()
                and (topic == 'culture' or item.get('has_editorial') is True)]
        if not pool:
            continue
        if topic == 'culture':
            latest = max(item['date'] for item in pool)
            pool = [item for item in pool if item['date'] == latest]
        pool.sort(key=lambda item: (item['date'], item['key']), reverse=True)
        position = (day.toordinal() * 2 + (slot.endswith('-pm'))) % len(pool)
        selected.append(pool[position])
    return selected


def notification_payload(published, topics, slot, base):
    if not safe_url(base):
        raise ValueError('Invalid public site URL')
    picked = selection(published, topics, slot)
    if not picked:
        return None
    names = ' · '.join(TOPICS[x['kind']] for x in picked)
    detail = str(picked[0].get('headline', 'Your reading selection'))[:130]
    return {'title': 'Your morning Brief' if slot.endswith('-am') else 'Your evening Brief',
            'body': f'{names}. {detail}',
            'url': base.rstrip('/') + '/notifications/read/index.html?' + urlencode({'items': ','.join(x['key'] for x in picked)}),
            'tag': 'brief-' + slot}


def deliver(db, row, slot, payload, keys, base, sender):
    sid = row['subscription_id']
    if not ENDPOINT.fullmatch(row.get('endpoint', '')):
        return 'invalid'
    if not db.rpc('brief_push_digest_claim', {'p_id': sid, 'p_slot': slot}).execute().data:
        return 'skipped'
    try:
        response = sender(subscription_info={'endpoint': row['endpoint'], 'keys': {'p256dh': row['p256dh'], 'auth': row['auth_key']}},
                          data=json.dumps(payload), vapid_private_key=keys['private_key'],
                          vapid_claims={'sub': 'https://' + urlsplit(base).netloc},
                          ttl=10800, timeout=15, requests_session=PushSession())
        if not 200 <= response.status_code < 300:
            raise RuntimeError('Push service did not accept delivery')
    except Exception as exc:
        # Never put endpoints, subscription keys or database error rows in logs.
        code = getattr(getattr(exc, 'response', None), 'status_code', None)
        if code in (404, 410):
            db.table('brief_push_subscriptions').delete().eq('subscription_id', sid).execute()
            return 'expired'
        db.table('brief_push_digest_deliveries').update({'state': 'failed', 'updated_at': datetime.now(timezone.utc).isoformat()}).eq('subscription_id', sid).eq('slot_key', slot).execute()
        return 'failed'
    # A successful send is never retried in this slot after being acknowledged.
    db.rpc('brief_push_digest_finish', {'p_id': sid, 'p_slot': slot}).execute()
    return 'sent'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', help='Read-only setup check. Never sends.')
    args = parser.parse_args()
    config = load_config(ROOT)
    base = config.get('site_url', '').rstrip('/')
    if not safe_url(base):
        raise ValueError('Set the public Brief URL first')
    db = client()
    # Intentionally fail clearly for missing migrations rather than a false green.
    rows = db.table('brief_push_config').select('*').eq('singleton', True).execute().data
    server_slot = db.rpc('brief_push_due_slot').execute().data
    if not rows or not rows[0]['enabled'] or not rows[0]['private_key']:
        print('::warning::Browser notifications are not ready. Run the SQL, then Build and Publish AIEO Brief to prepare the delivery keys.')
        return
    keys = rows[0]
    response = requests.get(base + '/data/current.json', timeout=(10, 45), headers={'Cache-Control': 'no-cache'})
    response.raise_for_status()
    published = response.json()
    if published.get('schema_version') != 'aieo_brief_public_v3':
        raise ValueError('The deployed Brief data is not in the expected format')
    pending = db.rpc('brief_push_digest_pending', {'p_slot': server_slot, 'p_limit': 500}).execute().data if server_slot else []
    if args.dry_run:
        now = datetime.now(AMSTERDAM)
        example_slot = server_slot or now.strftime('%Y-%m-%d-am')
        available = {kind: len(selection(published, [kind], example_slot)) for kind in TOPICS}
        print(json.dumps({'dry_run': True, 'timezone': 'Europe/Amsterdam', 'due_slot': server_slot,
                          'eligible_in_batch': len(pending), 'available_categories': available,
                          'keys_ready': bool(keys['public_key']), 'sent': 0}))
        return
    if not server_slot:
        print('Outside a morning/evening delivery window. No notifications sent.')
        return
    from pywebpush import webpush
    results = {}
    deadline = time.monotonic() + 480
    for row in pending:
        if time.monotonic() > deadline:
            break
        payload = notification_payload(published, row.get('topics', []), server_slot, base)
        state = deliver(db, row, server_slot, payload, keys, base, webpush) if payload else 'no_published_selection'
        results[state] = results.get(state, 0) + 1
    print(json.dumps({'slot': server_slot, 'results': results, 'batch_limit': 500}))
    if results.get('failed'):
        raise RuntimeError('Some deliveries failed; bounded retries are available in the next probe within this window')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'::error::Brief notifications failed ({type(error).__name__}). Check the Supabase migration, repository secrets and published data. No delivery credentials are printed.')
        raise SystemExit(1)
