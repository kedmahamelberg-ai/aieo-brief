#!/usr/bin/env python3
"""Validate prepared social packages; --audit additionally requires saved-UI evidence.

This does not publish, fetch credentials, or mistake a prepared asset for a saved post.
"""
import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from datetime import datetime
from zoneinfo import ZoneInfo


def validate(batch, audit=None, since=None, platform=None):
    topics = {x['id']: x for x in batch['topics']}
    errors = []
    seen = set()
    records = {x['id']: x for x in (audit or {}).get('items', [])}
    for item in batch['items']:
        p = item['platform']
        if p not in ('linkedin', 'facebook', 'instagram') or (platform and p != platform):
            continue
        if since and item['scheduled_at'] < since:
            continue
        ident = item['id']
        def require(ok, message):
            if not ok:
                errors.append(f'{ident}: {message}')
        t = topics[item['topic_id']]
        key = (p, item['scheduled_at'])
        require(key not in seen, 'duplicate platform/time')
        seen.add(key)
        dt = datetime.fromisoformat(item['scheduled_at'])
        require(dt.utcoffset() == dt.astimezone(ZoneInfo('Europe/Amsterdam')).utcoffset(), 'wrong Amsterdam offset')
        caption = item.get('caption', '')
        header = 'The brief AI research' if t['kind'] == 'Research' else f"The brief AI news from {t['country']}"
        cta = 'Read the research briefing on The Brief.' if t['kind'] == 'Research' else 'Read the full story on The Brief.'
        require(caption.startswith(header), 'missing exact series header')
        require(cta in caption, 'missing CTA')
        require(t['hook'] in caption and t['fact'] in caption, 'missing approved hook or explanation')
        require('–' not in caption and '—' not in caption, 'stylistic dash')
        tags = re.findall(r'(?<!\w)#[\w]+', caption)
        require(len(tags) == {'linkedin': 3, 'instagram': 5}.get(p, len(tags)) and (p != 'facebook' or 1 <= len(tags) <= 2), 'wrong hashtag count')
        require('#TheBrief' in tags or '#AIEO' in tags, 'missing brand hashtag')
        dest = urlparse(item.get('resolved_destination', ''))
        q = parse_qs(dest.query)
        require(dest.scheme == 'https' and dest.hostname == 'brief.hamelberg-ai.com', 'invalid article destination')
        require(dest.path.lstrip('/') == t['path'], 'destination does not match topic')
        require(q.get('utm_source') == [p] and all(q.get(k) for k in ('utm_medium', 'utm_campaign', 'utm_content')), 'missing or wrong tracking')
        assets = item.get('prepared_carousel_assets', [])
        expected_assets = 1 if p == 'linkedin' else 3
        require(len(assets) == expected_assets and all(Path(a).is_file() for a in assets), f'missing expected {expected_assets} image asset(s)')
        if p == 'linkedin':
            single_image = item.get('single_image_asset')
            require(single_image and Path(single_image).is_file(), 'missing LinkedIn single image')
            require(not item.get('document_asset'), 'LinkedIn PDF or document asset is prohibited')
        if p in ('linkedin', 'facebook'):
            require(item.get('visible_link', '').startswith('https://') and item['visible_link'] in caption, 'missing visible article link')
        else:
            require(not re.search(r'https?://|link in our matching Story', caption, re.I), 'Instagram caption has URL or nonexistent Story link')
            story = item.get('story', {})
            require(story.get('scheduled_at') == item['scheduled_at'], 'Story time mismatch')
            require(len(story.get('frames', [])) == 3 and all(Path(f).is_file() for f in story.get('frames', [])), 'missing Story frames')
            require(story.get('link_stickers_enabled') is False, 'Story sticker policy mismatch')
        if audit is not None:
            a = records.get(ident, {})
            require(a.get('status') == 'VERIFIED', 'saved post is unverified')
            for field in ('caption_verified', 'account_verified', 'media_order_verified', 'destination_verified'):
                require(a.get(field) is True, f'{field} not verified')
            expected_count = 1 if p == 'linkedin' else 3
            require(a.get('media_count') == expected_count, f'saved media count is not {expected_count}')
            require(a.get('media_type') == ('single_image' if p == 'linkedin' else 'photo_carousel'), 'saved media type differs from policy')
            require(a.get('scheduled_at') == item['scheduled_at'], 'saved schedule mismatch')
            require(a.get('evidence') and Path(a['evidence']).is_file(), 'missing saved-UI evidence')
            if p == 'instagram':
                require(a.get('story_frames_verified') == 3 and a.get('story_time_verified') is True, 'saved Stories unverified')
    return errors

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('batch', type=Path)
    p.add_argument('--audit', type=Path)
    p.add_argument('--since')
    p.add_argument('--platform', choices=['linkedin', 'facebook', 'instagram'])
    a = p.parse_args()
    errors = validate(json.loads(a.batch.read_text()), json.loads(a.audit.read_text()) if a.audit else None, a.since, a.platform)
    print('\n'.join(errors) if errors else 'PASS: selected package checks' + (' and saved-UI evidence' if a.audit else ' (live queue not certified)'))
    raise SystemExit(bool(errors))
