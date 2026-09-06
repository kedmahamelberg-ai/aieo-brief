#!/usr/bin/env python3
"""Check the deployed Observatory before starting a bounded Brief update."""
import argparse
import json
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import requests
from brief_contract import validate_pair, relationship_fingerprint
from build_site import inputs


def expected_period(now=None):
    today = (now or datetime.now(ZoneInfo('Europe/Amsterdam'))).date()
    end = today - timedelta(days=today.weekday() + 1)
    return (end - timedelta(days=6)).isoformat(), end.isoformat()


def needs_update(release, relationship, published):
    counts = validate_pair(release, relationship)
    return any((
        published.get('release_id') != release['release_id'],
        published.get('source_release_sha256') != release['content_sha256'],
        published.get('source_relationship_sha256') != relationship_fingerprint(relationship),
        published.get('directional_counts') != counts,
        published.get('story_count') != len(release['evidence']),
    ))


def brief_url():
    if os.environ.get('BRIEF_SITE_URL'):
        return os.environ['BRIEF_SITE_URL'].rstrip('/')
    owner, repo = os.environ.get('GITHUB_REPOSITORY', 'kedmahamelberg-ai/aieo-brief').split('/', 1)
    return f'https://{owner}.github.io/{repo}'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--require-current', action='store_true')
    args = parser.parse_args()
    release, relationship = inputs()
    response = requests.get(brief_url() + '/data/current.json', timeout=(10, 45), headers={'Cache-Control': 'no-cache'})
    if response.status_code == 404 and not args.require_current:
        published = {}
    else:
        response.raise_for_status()
        published = response.json()
    changed = needs_update(release, relationship, published)
    expected = expected_period()
    current = (release['period_start'], release['period_end']) == expected
    summary = {'observatory_edition': release['release_id'], 'period_start': release['period_start'],
               'period_end': release['period_end'], 'developments': len(release['evidence']),
               'brief_needs_update': changed, 'latest_completed_week': current}
    print(json.dumps(summary, indent=2))
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
            output.write(f'needs_update={str(changed).lower()}\n')
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as output:
            output.write(f"## Observatory → Brief\n\nEdition **{release['release_id']}**, {release['period_start']} to {release['period_end']}. "
                         f"{len(release['evidence'])} developments. {'Update required.' if changed else 'Both published editions match.'}\n")
    if args.require_current and (changed or not current):
        raise ValueError('The two live websites have not both published the latest complete week. Check the weekly pipeline and Follow Observatory Editions runs.')


if __name__ == '__main__':
    main()
