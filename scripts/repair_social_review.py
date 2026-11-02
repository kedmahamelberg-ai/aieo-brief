"""Repair the exact W45 artifact after a complete owner-requested source audit."""
import argparse
import copy
import hashlib
import json
import os
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path

import prepare_social_review as social
from social_review_delivery import ARTIFACT, review_html
from validate_social_package import validate

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / 'config/social-repair-2026-W45.json'


def read(path):
    return json.loads(path.read_text())


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def needed(plan, state):
    entry = state['editions'].get(plan['source_edition'])
    if not entry or entry['publication_week'] != plan['publication_week']:
        raise ValueError('The original edition receipt is missing or mismatched')
    match = ARTIFACT.fullmatch(entry['artifact_url'])
    if not match or match[1] != str(entry['run_id']):
        raise ValueError('Invalid original social artifact receipt')
    return int(entry.get('review_revision', 1)) < plan['revision'], match


def produce(folder, output, plan, *, items=None, verify_destinations=True):
    raw = (folder / 'batch.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != plan['baseline_batch_sha256']:
        raise ValueError('Repair input is not the exact audited original batch')
    baseline = json.loads(raw)
    if baseline['publishing_week'] != plan['publication_week'] or baseline['source_edition'] != plan['source_edition']:
        raise ValueError('Repair cannot move an article to a different edition')
    if len(plan['topic_updates']) != 15:
        raise ValueError('The complete 15-selection review is required')
    live = items is None
    items = json.loads(social.fetch(social.BASE + 'data/public-items.json'))['items'] if live else items
    available = {row['key']: row for row in items}
    topics = [copy.deepcopy(update['topic']) for update in plan['topic_updates']]
    for topic in topics:
        row = available.get(topic['source_key'])
        if not row or social.geography_fingerprint(row) != topic['article_content_sha256'] or row['path'] != topic['path']:
            raise ValueError('The live article has not reached the source-checked correction: ' + topic['id'])
        if not row.get('has_editorial') or not row.get('body_paragraphs'):
            raise ValueError('A headline-only destination cannot be promoted as a full Brief article')
        if topic['kind'] == 'News' and (row.get('edition') != plan['source_edition'] or topic['market'] not in social.verified_markets(row)):
            raise ValueError('Featured country or edition lacks source support: ' + topic['id'])
    output.mkdir(parents=True, exist_ok=True)
    for name in ('assets', 'sources'): (output / name).mkdir(exist_ok=True)
    photos = read(folder / 'PHOTO_MANIFEST.json')
    if len(photos) != 14 or len({photo['sha256'] for photo in photos.values()}) != 14:
        raise ValueError('The original photo provenance is incomplete')
    for photo in photos.values():
        relative = Path(photo['local_source'])
        if relative.is_absolute() or '..' in relative.parts or relative.parts[0] != 'sources':
            raise ValueError('Unsafe original photograph path')
        data = (folder / relative).read_bytes()
        if hashlib.sha256(data).hexdigest() != photo['sha256']:
            raise ValueError('Original W45 photograph bytes changed')
        (output / relative).write_bytes(data)
    replacements = plan.get('photo_replacements', {})
    history = read(ROOT / 'config/social-photo-history.json') if replacements else {}
    for key, photo in replacements.items():
        if key not in photos or photo['rights_status'] != 'CC0':
            raise ValueError('Unknown or unlicensed replacement photograph')
        relative = Path(photo['repository_source'])
        if relative.is_absolute() or '..' in relative.parts or relative.parts[:3] != ('config', 'social-repair-2026-W45', 'photos'):
            raise ValueError('Unsafe replacement photograph path')
        data = (ROOT / relative).read_bytes()
        if hashlib.sha256(data).hexdigest() != photo['sha256']:
            raise ValueError('Replacement photograph bytes changed')
        if photo['source_url'] in history['source_urls'] or photo['sha256'] in history['sha256']:
            raise ValueError('Replacement photograph was already used')
        destination = Path(photo['local_source'])
        if destination != Path(photos[key]['local_source']):
            raise ValueError('Replacement photograph must retain its existing safe package path')
        (output / destination).write_bytes(data)
        photos[key] = copy.deepcopy(photo)
    # Keep existing correct media byte-for-byte. Only revised copy is rendered.
    prior = {topic['id']: topic for topic in baseline['topics']}
    render = []
    visible_fields = ('hook', 'fact', 'kind', 'country')
    for update, topic in zip(plan['topic_updates'], topics):
        old = prior[update['previous_topic_id']]
        same_evidence = topic['kind'] != 'Research' or old.get('evidence') == topic.get('evidence')
        if topic.get('photo') not in replacements and old['id'] == topic['id'] and same_evidence and all(old.get(key) == topic.get(key) for key in visible_fields):
            for medium in ('carousel', 'story'):
                for card in (1, 2, 3):
                    relative = Path('assets') / f"{topic['id']}_{medium}_{card}.png"
                    shutil.copyfile(folder / relative, output / relative)
        else:
            render.append(topic)
    social.render(render, photos, output)
    monday = date.fromisoformat(min(topic['date'] for topic in topics))
    batch = social.build(topics, photos, output, plan['source_edition'], monday-timedelta(days=7), monday-timedelta(days=1), monday)
    batch['review_revision'] = plan['revision']
    batch['supersedes_batch_sha256'] = plan['baseline_batch_sha256']
    # The roundup must cover each featured country instead of accidentally
    # selecting several examples from the same countries by list position.
    roundup = [next(topic for topic in topics if topic.get('market') == market) for market in social.COUNTRIES]
    roundup.append(next(topic for topic in topics if topic['kind'] == 'Research'))
    batch['substack_post']['body'] = 'This week’s Brief selections cover five countries and one research Perspective.\n\n' + '\n\n'.join(topic['hook'] + '\n' + social.BASE + topic['path'] for topic in roundup)
    errors = validate(batch)
    if errors: raise ValueError('\n'.join(errors))
    checks = social.verify_links(batch) if verify_destinations else {'all_ok': False, 'test_only': True}
    social.review(batch, output)
    portable = json.loads(json.dumps(batch).replace(str(output.resolve()) + '/', ''))
    save(output / 'batch.json', portable)
    save(output / 'topics.json', topics)
    save(output / 'PHOTO_MANIFEST.json', photos)
    save(output / 'LINK_CHECK.json', checks)
    audit_path = ROOT / 'data/social-production/audits/2026-W45.json'
    if audit_path.exists():
        shutil.copyfile(audit_path, output / 'SOURCE_AUDIT.json')
    save(output / 'REPAIR_CHANGELOG.json', dict(revision=plan['revision'], before_sha256=plan['baseline_batch_sha256'],
         after_sha256=hashlib.sha256((output/'batch.json').read_bytes()).hexdigest(),
         changed_topic_ids=[topic['id'] for topic in render], replacements=[update for update in plan['topic_updates'] if update['replacement']]))
    if live and checks.get('all_ok'):
        save(output / 'READY_FOR_REVIEW.json', dict(status=social.STATUS, publication_week=plan['publication_week'],
             review_revision=plan['revision'], editorial_review_required=True, source_audit_complete=True,
             live_corrected_destinations_checked=True, created_at=datetime.now(social.ZONE).isoformat()))
    run_url = 'https://github.com/kedmahamelberg-ai/aieo-brief/actions/runs/' + os.environ.get('GITHUB_RUN_ID', '0')
    (output / 'BATCH_REVIEW.html').write_text(review_html(portable, output, run_url, review_url=run_url))
    return portable


def record(output, plan):
    ready = read(output / 'READY_FOR_REVIEW.json')
    if ready.get('source_audit_complete') is not True or ready.get('live_corrected_destinations_checked') is not True:
        raise ValueError('Only a repaired batch checked against the live corrected articles can be recorded')
    url = os.environ['SOCIAL_ARTIFACT_URL']
    if not ARTIFACT.fullmatch(url): raise ValueError('Invalid new artifact URL')
    state_path = ROOT / 'data/social-production/state.json'
    state = read(state_path)
    prior = copy.deepcopy(state['editions'][plan['source_edition']])
    state.setdefault('review_history', {}).setdefault(plan['source_edition'], []).append(prior)
    digest = hashlib.sha256((output / 'batch.json').read_bytes()).hexdigest()
    state['editions'][plan['source_edition']] = dict(publication_week=plan['publication_week'], status=social.STATUS,
         artifact_url=url, run_id=os.environ['GITHUB_RUN_ID'], review_revision=plan['revision'], batch_sha256=digest,
         created_at=datetime.now(social.ZONE).isoformat(), supersedes_artifact_url=prior['artifact_url'])
    approval_path = ROOT / 'data/social-production/approved' / (plan['publication_week'] + '.json')
    if approval_path.exists():
        approval = read(approval_path)
        history_path = ROOT / 'data/social-production/approval-history' / plan['publication_week'] / (approval['batch_sha256'] + '.json')
        save(history_path, approval)
        approval.update(status='SUPERSEDED_PENDING_CORRECTED_REVIEW', corrected_batch_sha256=digest,
                        superseded_at=datetime.now(social.ZONE).isoformat(), corrected_artifact_url=url)
        save(approval_path, approval)
    save(state_path, state)
    if plan.get('photo_replacements'):
        history_path = ROOT / 'config/social-photo-history.json'
        history = read(history_path)
        for photo in plan['photo_replacements'].values():
            for field, key in [('source_url', 'source_urls'), ('sha256', 'sha256')]:
                history[key] = sorted(set(history[key] + [photo[field]]))
        save(history_path, history)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['plan', 'produce', 'record'])
    parser.add_argument('--input', type=Path, default=ROOT / 'original-social-review')
    parser.add_argument('--output', type=Path, default=ROOT / 'social-review')
    args = parser.parse_args(); plan = read(PLAN)
    if args.action == 'plan':
        pending, match = needed(plan, read(ROOT / 'data/social-production/state.json'))
        if os.environ.get('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
                stream.write('needed=' + str(pending).lower() + '\nrun_id=' + match[1] + '\nartifact_id=' + match[2] + '\n')
        print(json.dumps({'repair_needed': pending, 'revision': plan['revision']}))
    elif args.action == 'produce': produce(args.input.resolve(), args.output.resolve(), plan)
    else: record(args.output, plan)


if __name__ == '__main__': main()
