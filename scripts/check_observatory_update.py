#!/usr/bin/env python3
"""Check the deployed Observatory before starting a bounded Brief update."""
import argparse
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
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


def needs_weekly_review(release, published):
    """Retry bounded editorial checks without regenerating all news summaries."""
    from weekly_editorials import START, VERSION
    if release['period_start'] < START:
        return False
    overview = published.get('weekly_overview') or {}
    if overview.get('release_id') != release['release_id'] or overview.get('editorial_version') != VERSION:
        return True
    return any(section.get('status') == 'pending'
               and section.get('pending_reason') in ('generation_pending', 'editorial_check_pending')
               and section.get('attempts', 0) < 3
               for section in (overview.get('markets', {}), overview.get('research', {})))


def missing_news_summaries(release, published):
    """Count source-ready stories in this edition that still lack Brief prose."""
    if published.get('release_id') != release['release_id']:
        return 0
    expected = {str(event.get('effective_event_id') or event['event_id'])
                for event in release['evidence']}
    return sum(str(story.get('event_id')) in expected
               and story.get('evidence_complete') is True
               and not story.get('has_editorial')
               for story in published.get('stories', []))


def needs_editorial_retry(release, published, status, now=None):
    """Resume time-deferred work promptly; pace repeated draft rejections daily."""
    if not missing_news_summaries(release, published):
        return False
    if status.get('release_id') != release['release_id']:
        return True
    try:
        last_attempt = datetime.fromisoformat(status['updated_at'].replace('Z', '+00:00'))
        if last_attempt.tzinfo is None:
            return True
        current = (now or datetime.now(ZoneInfo('Europe/Amsterdam'))).astimezone(ZoneInfo('Europe/Amsterdam'))
        local_attempt = last_attempt.astimezone(ZoneInfo('Europe/Amsterdam'))
        if status.get('counts', {}).get('deferred', 0) > 0:
            return (current - local_attempt).total_seconds() >= 2 * 3600
        return local_attempt.date() < current.date()
    except (KeyError, TypeError, ValueError):
        return True


def brief_url():
    if os.environ.get('BRIEF_SITE_URL'):
        return os.environ['BRIEF_SITE_URL'].rstrip('/')
    configured = json.loads((Path(__file__).resolve().parents[1] / 'config/site.json').read_text()).get('site_url')
    if configured:
        return configured.rstrip('/')
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
    weekly = needs_weekly_review(release, published)
    status_path = Path(__file__).resolve().parents[1] / 'data/editorial/status.json'
    status = json.loads(status_path.read_text()) if status_path.exists() else {}
    missing = missing_news_summaries(release, published)
    retry = needs_editorial_retry(release, published, status)
    expected = expected_period()
    current = (release['period_start'], release['period_end']) == expected
    summary = {'observatory_edition': release['release_id'], 'period_start': release['period_start'],
               'period_end': release['period_end'], 'developments': len(release['evidence']),
               'brief_needs_update': changed, 'weekly_review_needs_update': weekly,
               'missing_news_summaries': missing, 'news_retry_due': retry,
               'latest_completed_week': current}
    print(json.dumps(summary, indent=2))
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
            output.write(f'needs_update={str(changed).lower()}\n')
            output.write(f'needs_weekly_review={str(weekly).lower()}\n')
            output.write(f'needs_editorial_retry={str(retry).lower()}\n')
            output.write(f'missing_news_summaries={missing}\n')
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as output:
            output.write(f"## Observatory → Brief\n\nEdition **{release['release_id']}**, {release['period_start']} to {release['period_end']}. "
                         f"{len(release['evidence'])} developments. {'Update required.' if changed else 'Source editions match.'} "
                         f"**{missing} source-ready news summaries missing**; {'retry due' if retry else 'no retry due now'}.\n")
    if args.require_current and (changed or not current):
        raise ValueError('The two live websites have not both published the latest complete week. Check the weekly pipeline and Follow Observatory Editions runs.')


if __name__ == '__main__':
    main()
