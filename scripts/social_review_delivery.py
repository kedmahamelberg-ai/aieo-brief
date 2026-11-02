#!/usr/bin/env python3
"""Deliver the completed, unapproved social batch to the confirmed owner."""
from __future__ import annotations

import argparse
import base64
import hashlib
import html
import io
import json
import os
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
REPO = 'kedmahamelberg-ai/aieo-brief'
STATUS = 'DRAFT_NOT_APPROVED_DO_NOT_PUBLISH'
OWNER_EMAIL = 'kedma@hamelberg-ai.com'
ZONE = ZoneInfo('Europe/Amsterdam')
RECEIPTS = ROOT / 'data/social-production/email-receipts.json'
ARTIFACT = re.compile(r'https://github\.com/' + re.escape(REPO)
                      + r'/actions/runs/(\d+)/artifacts/(\d+)\Z')


def read(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def delivery_plan(state, receipts, today):
    week = today.strftime('%G-W%V')
    candidates = [(edition, entry) for edition, entry in state.get('editions', {}).items()
                  if entry.get('publication_week') == week and entry.get('status') == STATUS]
    if not candidates:
        return None
    if len(candidates) != 1:
        raise ValueError('Multiple completed social batches for this publication week')
    edition, entry = candidates[0]
    match = ARTIFACT.fullmatch(entry.get('artifact_url', ''))
    if not match or match[1] != str(entry.get('run_id')):
        raise ValueError('Invalid completed social artifact receipt')
    if week in receipts.get('weeks', {}):
        return None
    return dict(source_edition=edition, publication_week=week,
                artifact_url=entry['artifact_url'], run_id=match[1], artifact_id=match[2])


def load_batch(folder, plan):
    raw = (folder / 'batch.json').read_bytes()
    batch = json.loads(raw)
    ready = read(folder / 'READY_FOR_REVIEW.json', {})
    if (batch.get('status') != STATUS or ready.get('status') != STATUS
            or batch.get('publishing_week') != plan['publication_week']
            or ready.get('publication_week') != plan['publication_week']
            or batch.get('source_edition') != plan['source_edition']
            or batch.get('editorial_review_required') is not True
            or ready.get('editorial_review_required') is not True
            or batch.get('approval_phrase') != 'APPROVE SOCIAL WEEK ' + plan['publication_week']
            or len(batch.get('topics', [])) != 15 or len(batch.get('items', [])) != 60
            or any(item.get('status') != STATUS for item in batch['items'])):
        raise ValueError('Only the complete, matching, unapproved batch can be emailed')
    return batch, hashlib.sha256(raw).hexdigest()


def image_data(folder, relative, width=480):
    path = (folder / relative).resolve()
    if folder.resolve() not in path.parents or not path.is_file():
        raise ValueError('Review image is outside the downloaded package or missing')
    with Image.open(path) as image:
        image = image.convert('RGB')
        image.thumbnail((width, width * 2))
        buffer = io.BytesIO()
        image.save(buffer, format='JPEG', quality=72, optimize=True)
    return 'data:image/jpeg;base64,' + base64.b64encode(buffer.getvalue()).decode('ascii')


def review_html(batch, folder, artifact_url):
    esc = html.escape
    parts = ['<!doctype html><html lang="en"><meta charset="utf-8">',
             '<meta name="viewport" content="width=device-width,initial-scale=1">',
             '<title>The Brief social review ' + esc(batch['publishing_week']) + '</title>',
             '<style>body{font:16px/1.6 system-ui,sans-serif;max-width:1100px;margin:auto;padding:24px;color:#142d39;background:#f5f6f3}h1,h2,h3{line-height:1.25}section{padding:24px 0;border-bottom:1px solid #b9c7c6}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}a{color:#07626a}img{width:100%;height:auto}.media{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}summary{cursor:pointer;padding:12px 0}nav a{display:block}@media(max-width:600px){.media{grid-template-columns:1fr}}</style>',
             '<h1>The Brief · Social review ' + esc(batch['publishing_week']) + '</h1>',
             '<p><strong>DRAFT · NOT APPROVED · DO NOT PUBLISH</strong></p>',
             '<p>Source coverage: ' + esc(batch['source_dates']) + '. Times: Europe/Amsterdam.</p>',
             '<p><a href="' + esc(artifact_url, quote=True) + '">Download full-resolution media package on GitHub</a></p><nav>']
    for topic in batch['topics']:
        parts.append('<a href="#' + esc(topic['id'], quote=True) + '">' + esc(topic['date'] + ' ' + topic['time'] + ' · ' + topic['headline']) + '</a>')
    parts.append('<a href="#weekly-substack">Weekly Substack Post</a></nav>')
    for topic in batch['topics']:
        rows = [item for item in batch['items'] if item['topic_id'] == topic['id']]
        instagram = next(item for item in rows if item['platform'] == 'instagram')
        parts.extend(['<section id="' + esc(topic['id'], quote=True) + '">',
                      '<p>' + esc(topic['date'] + ' ' + topic['time'] + ' · ' + topic['kind'] + ' · ' + topic.get('country', '')) + '</p>',
                      '<h2>' + esc(topic['headline']) + '</h2>',
                      '<a href="https://brief.hamelberg-ai.com/' + esc(topic['path'], quote=True) + '">Read the Brief article</a>',
                      '<div class="media">'])
        for number, relative in enumerate(instagram['prepared_carousel_assets'], 1):
            parts.append('<figure><img alt="Carousel card ' + str(number) + '" src="' + image_data(folder, relative) + '"><figcaption>Carousel card ' + str(number) + '</figcaption></figure>')
        parts.append('</div><details><summary>Story frames</summary><div class="media">')
        for number, relative in enumerate(instagram['story']['frames'], 1):
            parts.append('<figure><img alt="Story frame ' + str(number) + '" src="' + image_data(folder, relative) + '"><figcaption>Story frame ' + str(number) + '</figcaption></figure>')
        parts.append('</div></details>')
        for item in rows:
            parts.append('<details><summary>' + esc(item['platform'].replace('_', ' ').title()) + ' · ' + esc(item['account']) + '</summary><pre>' + esc(item['caption']) + '</pre></details>')
        rights = rows[0].get('photo_rights')
        if rights:
            parts.append('<p>Illustrative photograph · ' + esc(rights['title']) + ' · ' + esc(rights['creator']) + ' · ' + esc(rights['rights_status']) + ' · <a href="' + esc(rights['source_url'], quote=True) + '">Rights source</a></p>')
        parts.append('<p>Evidence: ' + esc(topic.get('evidence', '')) + '</p><p>' + esc(topic.get('source_limitation', '')) + '</p>')
        for source in topic.get('source_urls', []):
            parts.append('<a href="' + esc(source, quote=True) + '">' + esc(source) + '</a><br>')
        parts.append('</section>')
    parts.append('<section id="weekly-substack"><h2>Weekly Substack Post</h2><h3>' + esc(batch['substack_post']['title']) + '</h3><pre>' + esc(batch['substack_post']['body']) + '</pre></section></html>')
    return ''.join(parts)


def email_content(batch, folder, artifact_url):
    esc = html.escape
    body = ['<h1>The Brief social approval batch ' + esc(batch['publishing_week']) + '</h1>',
            '<p><strong>DRAFT · NOT APPROVED · DO NOT PUBLISH</strong></p>',
            '<p>14 News selections, 1 Research selection, 60 platform drafts, Story frames and the weekly Substack Post.</p>',
            '<p>Coverage: ' + esc(batch['source_dates']) + '. All times Europe/Amsterdam.</p>',
            '<p>Open the attached BATCH_REVIEW.html for captions, carousel images, Story frames, evidence and photo credits. The Markdown copy is also attached.</p>',
            '<p><a href="' + esc(artifact_url, quote=True) + '">Download the complete batch and full-resolution media</a></p><ul>']
    for topic in batch['topics']:
        body.append('<li>' + esc(topic['date'] + ' ' + topic['time'] + ' · ' + topic['kind'] + ' · ' + topic['headline']) + '</li>')
    body.extend(['</ul><p>Review copy, claims, geography, photograph relevance and hashtags. Photographs are illustrative.</p>',
                 '<p>After review, give your publishing chat this explicit approval: <strong>' + esc(batch['approval_phrase']) + '</strong>.</p>',
                 '<p>This email requests review only. It does not approve, publish or schedule any social posts.</p>'])
    preview = review_html(batch, folder, artifact_url).encode()
    attachments = [dict(filename='BATCH_REVIEW.html', content=base64.b64encode(preview).decode('ascii')),
                   dict(filename='BATCH_REVIEW.md', content=base64.b64encode((folder / 'BATCH_REVIEW.md').read_bytes()).decode('ascii'))]
    return dict(subject='The Brief social batch ' + batch['publishing_week'] + ' — ready for your review', html=''.join(body), attachments=attachments)


def send(batch, folder, plan, digest, receipts):
    recipient = os.environ['WEEKLY_REVIEW_TO_EMAIL']
    if recipient != OWNER_EMAIL:
        raise ValueError('Social review recipient is not the confirmed owner address')
    response = requests.post('https://api.resend.com/emails', headers={
        'Authorization': 'Bearer ' + os.environ['RESEND_API_KEY'],
        'Idempotency-Key': 'brief-social-review-' + plan['publication_week'] + '-' + digest,
    }, json={'from': os.environ['RESEND_FROM_EMAIL'], 'to': [recipient],
             **email_content(batch, folder, plan['artifact_url'])}, timeout=60)
    response.raise_for_status()
    message_id = response.json().get('id')
    if not message_id:
        raise ValueError('Mail provider did not return a delivery ID')
    receipts.setdefault('weeks', {})[plan['publication_week']] = {
        **plan, 'batch_sha256': digest, 'provider_message_id': message_id,
        'accepted_at': datetime.now(ZONE).isoformat(), 'recipient': recipient,
        'status': 'accepted_by_email_provider',
    }
    RECEIPTS.parent.mkdir(parents=True, exist_ok=True)
    RECEIPTS.write_text(json.dumps(receipts, indent=2) + '\n')
    print('Social review email accepted for ' + plan['publication_week'] + '.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['plan', 'send', 'preview'])
    parser.add_argument('--folder', type=Path, default=ROOT / 'social-review')
    parser.add_argument('--preview-output', type=Path, default=ROOT / 'social-review-preview.html')
    args = parser.parse_args()
    state = read(ROOT / 'data/social-production/state.json', {})
    receipts = read(RECEIPTS, {'weeks': {}})
    plan = delivery_plan(state, {} if args.action == 'preview' else receipts, datetime.now(ZONE).date())
    if args.action == 'plan':
        if os.environ.get('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
                output.write('needed=' + str(plan is not None).lower() + '\n')
                if plan:
                    output.write('run_id=' + plan['run_id'] + '\nartifact_id=' + plan['artifact_id'] + '\n')
        print(json.dumps({'delivery_needed': plan is not None, 'plan': plan}))
        return
    if not plan:
        print('No unsent completed social batch for the current Amsterdam week.')
        return
    batch, digest = load_batch(args.folder, plan)
    if args.action == 'preview':
        args.preview_output.write_text(review_html(batch, args.folder, plan['artifact_url']))
    else:
        send(batch, args.folder, plan, digest, receipts)


if __name__ == '__main__':
    main()
