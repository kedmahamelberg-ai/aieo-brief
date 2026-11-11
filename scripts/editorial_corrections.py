"""Explicit, human-approved corrections; scheduled generation cannot replace them.

Only fields listed in the checked-in manifest are changed. Remove a lock through
review before regenerating a corrected item against new evidence.
"""
import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = 'data/editorial/approved-corrections-2026-10-26.json'
SOURCE_AUDITS = ('data/editorial/source-audit-corrections-2026-11-02.json',
                 'data/editorial/reading-corrections-2026-11-09.json',
                 'data/editorial/research-reading-corrections-2026-11-11.json')


def reading_proof(key, root=ROOT):
    path = Path(root) / 'data/editorial/reading-corrections-2026-11-09.json'
    if not path.exists():
        return None
    return next((row for row in json.loads(path.read_text()).get('news', [])
                 if row.get('key') == key and row.get('source_fingerprints')), None)


def corrections(root=ROOT):
    path = Path(root) / MANIFEST
    rows = {}
    if path.exists():
        manifest = json.loads(path.read_text())
        rows.update({('event:' + row['event_id']): row['after'] for row in manifest['news']})
        rows.update({row['key']: row['after'] for row in manifest.get('research', [])})
    # Explicitly registered source audits are corrective edits requested by
    # the owner. They never rewrite a separately signed weekly overview.
    for relative in SOURCE_AUDITS:
        audit_path = Path(root) / relative
        if not audit_path.exists():
            continue
        audit = json.loads(audit_path.read_text())
        if audit.get('schema_version') != 'brief_source_audit_corrections_v1':
            raise ValueError('Unknown source-audit correction schema')
        for row in audit.get('news', []) + audit.get('research', []):
            if not row.get('source_urls') or not row.get('reason'):
                raise ValueError('Source-audit correction lacks evidence or reason')
            rows.setdefault(row['key'], {}).update(row['after'])
    # This correction was approved and published before the batch audit.
    rows['event:4d7f1325-e2af-41e9-9895-47cd4674e836'] = {
        'deck': 'A France Travail document published by La Quadrature du Net outlines using a ChatGPT-style AI to assist job-centre controls, prompting mixed gains and concerns about data access and autonomy.',
        'limitation': 'Based on a project presentation published by La Quadrature du Net and the association’s analysis, with limited technical detail and no published outcomes.'}
    return rows


def is_locked(key, root=ROOT):
    path = Path(root) / MANIFEST
    pending = json.loads(path.read_text()).get('pending_keys', []) if path.exists() else []
    return key in corrections(root) or key in pending


def apply_corrections(rows, root=ROOT):
    approved = corrections(root)
    for row in rows:
        if row.get('key') in approved:
            row.update(copy.deepcopy(approved[row['key']]))
    return rows
