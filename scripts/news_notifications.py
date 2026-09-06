#!/usr/bin/env python3
"""Free Web Push delivery for consented readers, only after a live edition exists."""
import argparse
import base64
import json
import os
import re
import time
from urllib.parse import urlsplit
from datetime import datetime, timezone, timedelta
import requests
from supabase import create_client
from brief_contract import safe_url

ENDPOINT = re.compile(r'https://(?:fcm\.googleapis\.com/(?:fcm/send|wp)/|updates\.push\.services\.mozilla\.com/wpush/v[12]/|web\.push\.apple\.com/)[A-Za-z0-9_:/=+.-]+\Z')


def client():
    return create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SECRET_KEY'])


def ensure_keys(db):
    rows = db.table('brief_push_config').select('*').eq('singleton', True).execute().data
    if not rows or not rows[0]['enabled']:
        return None
    row = rows[0]
    if not row['private_key'] or not row['public_key']:
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import serialization
        key = ec.generate_private_key(ec.SECP256R1())
        private = base64.urlsafe_b64encode(key.private_bytes(serialization.Encoding.DER,
            serialization.PrivateFormat.PKCS8, serialization.NoEncryption())).decode().rstrip('=')
        public = base64.urlsafe_b64encode(key.public_key().public_bytes(serialization.Encoding.X962,
            serialization.PublicFormat.UncompressedPoint)).decode().rstrip('=')
        # Conditional update: a second simultaneous build must not rotate keys.
        db.table('brief_push_config').update({'private_key': private, 'public_key': public}).eq('singleton', True).eq('private_key', '').execute()
        row = db.table('brief_push_config').select('*').eq('singleton', True).single().execute().data
    return row


def public_settings(config, preview=False):
    if preview or not config.get('supabase_publishable_key'):
        return {'enabled': False}
    try:
        row = ensure_keys(client())
        return {'enabled': bool(row), 'public_key': row['public_key'] if row else ''}
    except Exception:
        # Never print the PostgREST error or private key values.
        print('::warning::News notifications are unavailable. Check the notifications SQL setup; the website can still publish.')
        return {'enabled': False}


def notification_payload(published, base):
    if not safe_url(base) or not re.fullmatch(r'\d{4}-W\d{2}', published.get('release_id', '')):
        raise ValueError('Invalid published edition for notifications.')
    start = datetime.fromisoformat(published['period_start']).strftime('%d %b').lstrip('0')
    end = datetime.fromisoformat(published['period_end']).strftime('%d %b').lstrip('0')
    return {'title': 'Your new AI news edition is ready',
            'body': f"{start}–{end}. Explore {published['story_count']} developments across five markets.",
            'url': base.rstrip('/') + '/', 'tag': 'brief-edition-' + published['release_id']}


class PushSession(requests.Session):
    def post(self, url, **kwargs):
        if not ENDPOINT.fullmatch(url):
            raise ValueError('Unsupported browser push service.')
        kwargs['allow_redirects'] = False
        return super().post(url, **kwargs)


def deliver(db, row, release_id, payload, keys, base, sender):
    sid = row['subscription_id']
    if not ENDPOINT.fullmatch(row['endpoint']):
        return 'invalid'
    if not db.rpc('brief_push_claim', {'p_id': sid, 'p_release': release_id}).execute().data:
        return 'skipped'
    from pywebpush import WebPushException
    try:
        response = sender(subscription_info={'endpoint': row['endpoint'], 'keys': {'p256dh': row['p256dh'], 'auth': row['auth_key']}},
            data=json.dumps(payload), vapid_private_key=keys['private_key'],
            vapid_claims={'sub': 'https://' + urlsplit(base).netloc}, ttl=86400,
            timeout=15, requests_session=PushSession())
        if not 200 <= response.status_code < 300:
            raise RuntimeError('Push service did not accept the notification.')
    except Exception as exc:
        code = getattr(getattr(exc, 'response', None), 'status_code', None)
        if isinstance(exc, WebPushException) and code in (404, 410):
            db.table('brief_push_subscriptions').delete().eq('subscription_id', sid).execute()
            return 'expired'
        db.table('brief_push_deliveries').update({'state': 'failed', 'updated_at': datetime.now(timezone.utc).isoformat()}).eq('subscription_id', sid).eq('release_id', release_id).execute()
        return 'failed'
    db.rpc('brief_push_finish', {'p_id': sid, 'p_release': release_id}).execute()
    return 'sent'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    # No account connection, no notification work and no secret generation.
    if not os.environ.get('SUPABASE_PUBLISHABLE_KEY'):
        print('News alerts are not connected; no notifications sent.')
        return
    from check_observatory_update import brief_url
    from pywebpush import webpush
    base = brief_url()
    response = requests.get(base + '/data/current.json', timeout=(10, 45), headers={'Cache-Control': 'no-cache'})
    response.raise_for_status()
    published = response.json()
    payload = notification_payload(published, base)
    db = client()
    try:
        rows = db.table('brief_push_config').select('*').eq('singleton', True).execute().data
    except Exception:
        print('::warning::Notifications SQL has not been installed; no notifications sent.')
        return
    if not rows or not rows[0]['enabled'] or not rows[0]['private_key']:
        print('News alerts are disabled or not yet prepared.')
        return
    keys = rows[0]
    release_id = published['release_id']
    # Refuse a stale CDN response, and never notify about corrections to the
    # same edition. New subscribers start at the edition already published.
    if keys['last_release'] > release_id:
        print('Waiting for the current deployed edition.'); return
    subscriptions = db.rpc('brief_push_pending', {'p_release': release_id, 'p_limit': 500}).execute().data
    if args.dry_run:
        print(json.dumps({'release': release_id, 'eligible_in_batch': len(subscriptions), 'dry_run': True})); return
    db.table('brief_push_config').update({'last_release': release_id, 'updated_at': datetime.now(timezone.utc).isoformat()}).eq('singleton', True).execute()
    results = {}
    deadline = time.monotonic() + 480
    for row in subscriptions:
        if time.monotonic() > deadline:
            break
        state = deliver(db, row, release_id, payload, keys, base, webpush)
        results[state] = results.get(state, 0) + 1
    cutoff = (datetime.now(timezone.utc)-timedelta(days=180)).isoformat()
    db.table('brief_push_subscriptions').delete().lt('updated_at', cutoff).execute()
    db.table('brief_push_deliveries').delete().lt('updated_at', (datetime.now(timezone.utc)-timedelta(days=30)).isoformat()).execute()
    print(json.dumps({'release': release_id, 'results': results}))
    if results.get('failed'):
        raise RuntimeError('Some push services did not accept delivery. The next automatic pass will retry within the attempt limit.')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Database exceptions may include a failing row. Keep delivery
        # endpoints and key material out of public GitHub workflow logs.
        print(f'::error::News notification processing failed ({type(error).__name__}). Check the notification setup and the next automatic retry.')
        raise SystemExit(1)
