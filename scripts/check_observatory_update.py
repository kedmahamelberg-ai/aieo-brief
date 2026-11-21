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
from source_chronology import public_event_ids, public_directional_counts
from editorial_corrections import corrections
from daily_selection import reading_day


def expected_period(now=None):
    today = (now or datetime.now(ZoneInfo('Europe/Amsterdam'))).date()
    end = today - timedelta(days=today.weekday() + 1)
    return (end - timedelta(days=6)).isoformat(), end.isoformat()


def expected_brief_counts(release, relationship):
    """Apply the same approved direction overrides used by the Brief publisher."""
    counts = public_directional_counts(release, relationship)
    eligible = public_event_ids(release)
    approved = corrections()
    for row in relationship['evidence']:
        event_id = str(row['event_id'])
        if event_id not in eligible:
            continue
        override = approved.get('event:' + event_id, {})
        for axis in counts:
            before = row['axes'][axis]['direction']
            after = override.get(axis + '_direction', before)
            if after not in counts[axis]:
                raise ValueError('Invalid approved ' + axis + ' direction: ' + event_id)
            counts[axis][before] -= 1
            counts[axis][after] += 1
    return counts


def needs_update(release, relationship, published):
    validate_pair(release, relationship)
    counts = expected_brief_counts(release, relationship)
    return any((
        published.get('release_id') != release['release_id'],
        published.get('source_release_sha256') != release['content_sha256'],
        published.get('source_relationship_sha256') != relationship_fingerprint(relationship),
        published.get('directional_counts') != counts,
        published.get('story_count') != len(public_event_ids(release)),
    ))


def needs_daily_refresh(published, now=None):
    """Refresh the calendar pages even when the source edition is unchanged."""
    return (published.get('daily_selection') or {}).get('selection_date') != reading_day(now).isoformat()


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
    expected = public_event_ids(release)
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
    counts = status.get('counts') or {}
    # A source-only page is not a reason to call the model again when every
    # source-ready draft was already rejected for the same unchanged evidence.
    if counts.get('selected') == 0 and counts.get('deferred', 0) == 0:
        return False
    try:
        last_attempt = datetime.fromisoformat(status['updated_at'].replace('Z', '+00:00'))
        if last_attempt.tzinfo is None:
            return True
        current = (now or datetime.now(ZoneInfo('Europe/Amsterdam'))).astimezone(ZoneInfo('Europe/Amsterdam'))
        local_attempt = last_attempt.astimezone(ZoneInfo('Europe/Amsterdam'))
        # Older targeted runs did not record their unselected remainder as
        # deferred. Do not let one repaired article postpone all other stories
        # until tomorrow merely because its targeted pass has finished.
        remaining = max(0, counts.get('needs_model', 0) + counts.get('needs_rebind', 0)
                        - counts.get('blocked_rejections', 0) - counts.get('selected', 0))
        if counts.get('deferred', 0) > 0 or remaining > 0:
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
    daily = needs_daily_refresh(published)
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
               'daily_pages_need_refresh': daily,
               'missing_news_summaries': missing, 'news_retry_due': retry,
               'latest_completed_week': current}
    print(json.dumps(summary, indent=2))
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
            output.write(f'needs_update={str(changed).lower()}\n')
            output.write(f'needs_daily_refresh={str(daily).lower()}\n')
            output.write(f'needs_weekly_review={str(weekly).lower()}\n')
            output.write(f'needs_editorial_retry={str(retry).lower()}\n')
            output.write(f'missing_news_summaries={missing}\n')
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as output:
            output.write(f"## Observatory → Brief\n\nEdition **{release['release_id']}**, {release['period_start']} to {release['period_end']}. "
                         f"{len(release['evidence'])} developments. {'Update required.' if changed else 'Source editions match.'} "
                         f"{'Daily calendar refresh required.' if daily else 'Daily pages are current.'} "
                         f"**{missing} source-ready news summaries missing**; {'retry due' if retry else 'no retry due now'}.\n")
    if args.require_current and (changed or not current):
        raise ValueError('The two live websites have not both published the latest complete week. Check the weekly pipeline and Follow Observatory Editions runs.')


if __name__ == '__main__':
    main()
