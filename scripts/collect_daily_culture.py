#!/usr/bin/env python3
"""Publish five attributed works from the stored library. No daily scraping."""
import argparse
import json
import os
from pathlib import Path
from culture_library import ROOT, publication, summary
from daily_selection import reading_day


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', default=reading_day().isoformat())
    parser.add_argument('--refresh', action='store_true', help='Rebuild the same deterministic selection')
    args = parser.parse_args()
    data = publication(args.date, ROOT)
    if not data['items']:
        print('Daily culture is disabled.')
        return
    folder = ROOT / 'data/culture'
    folder.mkdir(parents=True, exist_ok=True)
    info = summary(ROOT)
    # Only write after all five selections and their cached image have passed.
    temporary = folder / 'current.tmp'
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    os.replace(temporary, folder / 'current.json')
    status = {'date': args.date, 'status': 'complete', 'selection_method': 'stored_calendar',
              'source_network_calls': 0, 'daily_items': 5, 'library_items': info['total'],
              'cycle_days': info['cycle_days']}
    (folder / 'status.json').write_text(json.dumps(status, indent=2) + '\n')
    print(json.dumps(status, indent=2))
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as output:
            output.write(f"## Daily pause · {args.date}\n\nFive selections from the stored {info['total']:,}-entry collection. No source websites contacted.\n")


if __name__ == '__main__':
    main()
