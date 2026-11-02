"""Flag news presented as recent when every dated source URL is older."""
from __future__ import annotations

import re
from urllib.parse import urlparse


def dated_source_year(url):
    """Return a year only for a publication-year path segment near the URL root."""
    parts = [part for part in urlparse(str(url or '')).path.split('/') if part]
    for part in parts[:4]:
        if re.fullmatch(r'20\d{2}', part):
            return int(part)
    return None


def older_source_year(event):
    """Return the older year when every linked source URL supplies one."""
    event_year = str(event.get('event_date') or '')[:4]
    if not re.fullmatch(r'20\d{2}', event_year):
        return None
    sources = event.get('sources') or []
    years = [dated_source_year(source.get('url')) for source in sources]
    if years and all(year is not None and year < int(event_year) for year in years):
        return max(years)
    return None


def public_event_ids(release):
    """IDs eligible for the current Brief edition after date checks."""
    return {str(event.get('effective_event_id') or event['event_id'])
            for event in release['evidence'] if not older_source_year(event)}


def public_directional_counts(release, relationship):
    """Count published cards, while the full Observatory pair is validated elsewhere."""
    from brief_contract import DIRECTIONS
    eligible = public_event_ids(release)
    counts = {axis: {direction: 0 for direction in sorted(DIRECTIONS)}
              for axis in ('human', 'ai')}
    for row in relationship['evidence']:
        if str(row['event_id']) not in eligible:
            continue
        for axis in counts:
            counts[axis][row['axes'][axis]['direction']] += 1
    return counts
