"""Week-level approval/publication lock shared by social workflows (stdlib only)."""
import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
TERMINAL = {'APPROVED', 'PUBLISHED', 'SCHEDULED', 'PUBLISHED_AND_SCHEDULED'}


def read(path):
    return json.loads(path.read_text()) if path.exists() else {}


def completed_week(root, week, state=None):
    """An approval belongs to the publication week, not an artifact or renderer version."""
    if not re.fullmatch(r'\d{4}-W\d{2}', week):
        raise ValueError('Invalid social publication week')
    directory = root / 'data/social-production'
    for category in ('approved', 'published'):
        receipt = read(directory / category / (week + '.json'))
        if receipt and receipt.get('publication_week', week) != week:
            raise ValueError('Mismatched social completion receipt')
        if receipt.get('status') in TERMINAL or receipt.get('publishing_status') in TERMINAL:
            return True
    state = read(directory / 'state.json') if state is None else state
    return any(entry.get('publication_week') == week and
               (entry.get('status') in TERMINAL or entry.get('publishing_status') in TERMINAL)
               for entry in state.get('editions', {}).values())


def blocked_week(root, week):
    """A suppression blocks duplicate work without granting publication approval."""
    if not re.fullmatch(r'\d{4}-W\d{2}', week):
        raise ValueError('Invalid social publication week')
    marker = read(root / 'data/social-production/blocked' / (week + '.json'))
    if marker and (marker.get('publication_week') != week or marker.get('status') != 'BLOCK_DUPLICATE'):
        raise ValueError('Invalid social duplicate-block marker')
    return bool(marker)


def locked_week(root, week, state=None):
    return blocked_week(root, week) or completed_week(root, week, state)


def require_unfinished(root, week):
    if blocked_week(root, week):
        raise ValueError('Social week ' + week + ' is blocked to prevent a duplicate')
    if completed_week(root, week):
        raise ValueError('Social week ' + week + ' is already approved or published; refusing a duplicate')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', type=Path, help='Use the repair plan publication week')
    args = parser.parse_args()
    week = (read(args.plan)['publication_week'] if args.plan else
            datetime.now(ZoneInfo('Europe/Amsterdam')).strftime('%G-W%V'))
    needed = not locked_week(ROOT, week)
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
            stream.write('needed=' + str(needed).lower() + '\n')
    print(json.dumps({'publication_week': week, 'unfinished': needed}))


if __name__ == '__main__':
    main()
