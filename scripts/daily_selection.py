"""Calendar-based reading order. Source dates and classification data never change."""
from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

TIMEZONE = 'Europe/Amsterdam'


def reading_day(now=None):
    now = now or datetime.now(ZoneInfo(TIMEZONE))
    return now.astimezone(ZoneInfo(TIMEZONE)).date()


def score(value):
    return hashlib.sha256(value.encode()).hexdigest()


def balanced_order(items, edition):
    """Assign multi-market stories once, then alternate discovery markets."""
    groups = defaultdict(list)
    for item in sorted(items, key=lambda x: score(edition + x['key'])):
        markets = item.get('markets') or ['other']
        market = min(markets, key=lambda m: (len(groups[m]), m))
        groups[market].append(item)
    for rows in groups.values():
        rows.sort(key=lambda x: (not x.get('evidence_complete'),
                                 not x.get('has_editorial'), score(edition + x['key'])))
    order = []
    while any(groups.values()):
        for market in sorted(groups):
            if groups[market]:
                order.append(groups[market].pop(0))
    return order


def rotation_plan(items, edition, period_end, today=None):
    """Seven distinct starting batches; every current story remains available."""
    today = today or reading_day()
    if isinstance(today, str):
        today = date.fromisoformat(today)
    anchor = date.fromisoformat(period_end) + timedelta(days=1)
    ordered = balanced_order(items, edition)
    layouts = []
    for slot in range(7):
        # Partition the full edition across seven days, without dropping remainders.
        offset = slot * len(ordered) // 7
        rotated = ordered[offset:] + ordered[:offset]
        # Feature complete source accounts first within this day's new batch.
        end = (slot + 1) * len(ordered) // 7
        batch_size = max(1, end - offset)
        batch = rotated[:batch_size]
        candidates = [x for x in batch if x.get('evidence_complete')] or batch
        lead = candidates[0] if candidates else None
        highlights = []
        seen = set(lead.get('markets', []) if lead else [])
        for item in (candidates[1:] + batch + rotated):
            if item is lead or item in highlights:
                continue
            if len(highlights) < 2 and (set(item.get('markets', [])) - seen or not item.get('markets')):
                highlights.append(item)
                seen.update(item.get('markets', []))
        for item in rotated:
            if len(highlights) == min(2, max(0, len(rotated) - 1)):
                break
            if item is not lead and item not in highlights:
                highlights.append(item)
        layouts.append({'lead': lead['key'] if lead else None,
                        'highlights': [x['key'] for x in highlights],
                        'order': [x['key'] for x in rotated]})
    slot = (today - anchor).days % 7
    return {'timezone': TIMEZONE, 'selection_date': today.isoformat(),
            'anchor': anchor.isoformat(), 'edition': edition,
            'slot': slot, 'layouts': layouts}
