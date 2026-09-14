#!/usr/bin/env python3
"""Append an approved social batch to the permanent, versioned short-link registry."""
import argparse
import json
import re
from pathlib import Path
from short_links import article_alias

ROOT = Path(__file__).resolve().parents[1]

def import_batch(batch, existing):
    week = batch['publishing_week']
    if not re.fullmatch(r'20\d{2}-W\d{2}', week):
        raise ValueError('Invalid publishing week')
    prefix = week[2:].lower().replace('-', '')
    by_slug = {x['slug']: x for x in existing}
    if len(by_slug) != len(existing):
        raise ValueError('Duplicate existing address')
    for n, topic in enumerate(batch['topics'], 1):
        article_alias(topic['path'])  # Validate the local article path.
        for platform, suffix in [('facebook', 'f'), ('linkedin', 'l')]:
            entry = {'slug':f'{prefix}-{n}{suffix}', 'article_path':topic['path'], 'tracking':{'utm_source':platform, 'utm_medium':'organic_social', 'utm_campaign':'brief_'+week.lower().replace('-', '_'), 'utm_content':topic['id']}}
            previous = by_slug.get(entry['slug'])
            if previous and previous != entry:
                raise ValueError('Refusing to change an existing short address: '+entry['slug'])
            by_slug[entry['slug']] = entry
    return list(by_slug.values())

if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('batch',type=Path);args=parser.parse_args()
    path=ROOT/'config/social-links.json'
    previous=json.loads(path.read_text()).get('links',[]) if path.exists() else []
    links=import_batch(json.loads(args.batch.read_text()),previous)
    path.write_text(json.dumps({'links':links},indent=2)+'\n')
    print(f'{len(links)} permanent campaign addresses retained')
