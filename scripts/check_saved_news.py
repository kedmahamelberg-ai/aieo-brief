"""Release accepted news checkpoints without starting a writer or model."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import requests

from brief_database import dbmaps
from build_site import cards, inputs, apply_current_source_corrections
from check_observatory_update import brief_url

ROOT = Path(__file__).resolve().parents[1]


def newly_available(current, published):
    live = {item['event_id']: item for item in published.get('stories', [])}
    return [item['event_id'] for item in current
            if item.get('has_editorial') and item.get('what_happened')
            and item.get('body_paragraphs')
            and not live.get(item['event_id'], {}).get('has_editorial')]


def publication_busy(runs, fetch_jobs):
    for run in runs:
        if run.get('status') == 'completed':
            continue
        if run.get('name') == 'Build and Publish AIEO Brief':
            return True
        if run.get('name') == 'Follow Observatory Editions':
            jobs = fetch_jobs(run['jobs_url'])
            if any(job.get('status') in ('queued', 'in_progress')
                   and job.get('name', '').startswith('publish /') for job in jobs):
                return True
    return False


def main():
    repository = os.environ.get('GITHUB_REPOSITORY', 'kedmahamelberg-ai/aieo-brief')
    headers = {'Accept': 'application/vnd.github+json',
               'Authorization': 'Bearer ' + os.environ['GITHUB_TOKEN']}
    with requests.Session() as session:
        response = session.get('https://api.github.com/repos/' + repository
                               + '/actions/runs?per_page=100', headers=headers, timeout=30)
        response.raise_for_status()
        def jobs(url):
            result = session.get(url, headers=headers, timeout=30)
            result.raise_for_status()
            return result.json()['jobs']
        busy = publication_busy(response.json()['workflow_runs'], jobs)
        pending = []
        if not busy:
            release, relationship = inputs()
            registry, readiness, editorial = dbmaps(False)
            proof_path = ROOT / 'data/editorial/release-source-fingerprints.json'
            proofs = json.loads(proof_path.read_text()) if proof_path.exists() else {}
            current = cards(release, relationship, registry, readiness, editorial,
                            legacy_proofs=proofs)
            apply_current_source_corrections(current, release['release_id'])
            result = session.get(brief_url() + '/data/current.json',
                                 params={'checkpoint_check': int(time.time())},
                                 headers={'Cache-Control': 'no-cache'}, timeout=30)
            result.raise_for_status()
            pending = newly_available(current, result.json())
    report = {'publication_busy': busy, 'accepted_articles_not_live': None if busy else len(pending),
              'event_ids': pending, 'needs_publish': bool(pending)}
    print(json.dumps(report, indent=2))
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
            output.write('needs_publish=' + str(bool(pending)).lower() + '\n')
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as output:
            output.write('Checkpoint comparison skipped: another publisher is active.\n' if busy
                         else 'Accepted news checkpoint: ' + str(len(pending))
                         + ' completed articles awaiting publication.\n')


if __name__ == '__main__':
    main()
