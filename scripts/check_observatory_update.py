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
from source_chronology import public_event_ids
from editorial_corrections import apply_corrections
from news_reading import prepare_display, EFFECT_LABELS

ROOT = Path(__file__).resolve().parents[1]


def expected_period(now=None):
    today = (now or datetime.now(ZoneInfo('Europe/Amsterdam'))).date()
    end = today - timedelta(days=today.weekday() + 1)
    return (end - timedelta(days=6)).isoformat(), end.isoformat()


def publication_differences(release, relationship, published, root=ROOT):
    """Check source bindings and the exact corrected articles, not raw totals alone."""
    validate_pair(release, relationship)
    eligible = public_event_ids(release)
    expected_metadata = {
        'release_id': release['release_id'],
        'period_start': release['period_start'],
        'period_end': release['period_end'],
        'source_release_sha256': release['content_sha256'],
        'source_relationship_sha256': relationship_fingerprint(relationship),
        'story_count': len(eligible),
    }
    differences = [field for field, value in expected_metadata.items()
                   if published.get(field) != value]
    stories = published.get('stories')
    if not isinstance(stories, list) or any(not isinstance(row, dict) for row in stories):
        return differences + ['stories_missing_or_invalid']
    ids = [str(row.get('event_id') or '') for row in stories]
    if len(ids) != len(set(ids)):
        differences.append('duplicate_article_ids')
    if set(ids) != eligible:
        differences.append('article_inventory')
    if len(stories) != len(eligible):
        differences.append('article_count')
    by_id = dict(zip(ids, stories))
    expected = []
    for row in relationship['evidence']:
        event_id = str(row['event_id'])
        if event_id not in eligible:
            continue
        axes = row['axes']
        story = by_id.get(event_id, {})
        expected.append({
            'key': 'event:' + event_id, 'event_id': event_id, 'kind': 'news',
            'human_direction': axes['human']['direction'],
            'ai_direction': axes['ai']['direction'],
            # The builder maps an empty published box to Context. Editorial
            # wording can differ from upstream evidence; never copy its label.
            'for_humans': story.get('for_humans', ''),
            'for_ai': story.get('for_ai', ''),
            # Match the builder's exception for a validated reading that replaces
            # a temporary access notice. Other published labels are never trusted
            # as the expected classification.
            'has_editorial': story.get('has_editorial'),
            'access_recovery_validated': story.get('access_recovery_validated'),
        })
    # Reuse the same registered corrections and display rules as publication.
    # Do not apply corrections to the published rows: that would hide stale data.
    apply_corrections(expected, root)
    prepare_display(expected)
    mismatches = []
    for row in expected:
        story = by_id.get(row['event_id'], {})
        for axis in ('human', 'ai'):
            field = axis + '_direction'
            if story.get(field) != row[field]:
                mismatches.append(row['event_id'] + ':' + axis)
    if mismatches:
        differences.append('article_classifications: ' + ', '.join(mismatches))
    actual_counts = {axis: {direction: 0 for direction in sorted(EFFECT_LABELS)}
                     for axis in ('human', 'ai')}
    for story in stories:
        for axis in actual_counts:
            direction = story.get(axis + '_direction')
            if isinstance(direction, str) and direction in actual_counts[axis]:
                actual_counts[axis][direction] += 1
    if published.get('directional_counts') != actual_counts:
        differences.append('directional_counts_do_not_match_articles')
    return differences


def needs_update(release, relationship, published, root=ROOT):
    return bool(publication_differences(release, relationship, published, root))


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
    differences = publication_differences(release, relationship, published)
    changed = bool(differences)
    weekly = needs_weekly_review(release, published)
    status_path = Path(__file__).resolve().parents[1] / 'data/editorial/status.json'
    status = json.loads(status_path.read_text()) if status_path.exists() else {}
    missing = missing_news_summaries(release, published)
    retry = needs_editorial_retry(release, published, status)
    expected = expected_period()
    current = (release['period_start'], release['period_end']) == expected
    summary = {'observatory_edition': release['release_id'], 'period_start': release['period_start'],
               'period_end': release['period_end'], 'developments': len(release['evidence']),
               'brief_needs_update': changed, 'publication_differences': differences,
               'weekly_review_needs_update': weekly,
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
                         f"{len(release['evidence'])} developments. {'Update required.' if changed else 'Source editions and corrected article classifications match.'} "
                         f"**{missing} source-ready news summaries missing**; {'retry due' if retry else 'no retry due now'}.\n")
            if differences:
                output.write('\nDifferences: ' + '; '.join(differences) + '\n')
    if args.require_current and (changed or not current):
        reasons = differences + ([] if current else ['observatory_period_not_latest_completed_week'])
        raise ValueError('Live edition verification failed: ' + '; '.join(reasons))


if __name__ == '__main__':
    main()
