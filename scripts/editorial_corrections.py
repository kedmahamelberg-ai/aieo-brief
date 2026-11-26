"""Explicit, human-approved corrections; scheduled generation cannot replace them.

Only fields listed in the checked-in manifest are changed. Remove a lock through
review before regenerating a corrected item against new evidence.
"""
import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = 'data/editorial/approved-corrections-2026-10-26.json'
CITATION_MANIFEST = 'data/editorial/source-citation-corrections-2026-11-22.json'
SOURCE_AUDITS = ('data/editorial/source-audit-corrections-2026-11-02.json',
                 'data/editorial/reading-corrections-2026-11-09.json',
                 'data/editorial/research-reading-corrections-2026-11-11.json',
                 'data/editorial/plain-language-corrections-2026-11-12.json',
                 'data/editorial/concise-box-corrections-2026-11-13.json',
                 'data/editorial/article-access-corrections-2026-11-15.json',
                 'data/editorial/w46-completion-corrections-2026-11-16.json',
                 'data/editorial/prose-review-2026-11-17.json',
                 'data/editorial/source-citation-corrections-2026-11-21.json',
                 CITATION_MANIFEST,
                 'data/editorial/research-stub-corrections-2026-11-22.json',
                 'data/editorial/w47-prose-corrections-2026-11-23.json',
                 'data/editorial/research-scope-corrections-2026-11-25.json',
                 'data/editorial/research-source-corrections-2026-11-26.json')


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


def reviewed_source_url_sets(root=ROOT):
    """Source identities recorded with approved news corrections, by event key."""
    identities = {}
    for relative in SOURCE_AUDITS:
        path = Path(root) / relative
        if not path.exists():
            continue
        for record in json.loads(path.read_text()).get('news', []):
            key = record.get('key')
            if not key:
                continue
            for sources in (record.get('source_urls') or [],
                            (record.get('after') or {}).get('sources') or []):
                urls = tuple(source.get('url') if isinstance(source, dict) else source
                             for source in sources)
                if urls and all(urls):
                    identities.setdefault(key, set()).add(urls)
    return identities


def recoverable_keys(root=ROOT):
    path = Path(root) / 'data/editorial/article-access-corrections-2026-11-15.json'
    if not path.exists(): return set()
    recoverable = {row['key'] for row in json.loads(path.read_text()).get('news', [])
                   if row.get('retry_when_full_source_available') is True}
    reviewed_path = Path(root) / 'data/editorial/prose-review-2026-11-17.json'
    if reviewed_path.exists():
        # A later owner-reviewed full reading or prose edit supersedes the old
        # temporary access notice, including already recovered stored versions.
        recoverable -= {row['key'] for row in json.loads(reviewed_path.read_text()).get('news', [])}
    return recoverable


def is_locked(key, root=ROOT):
    path = Path(root) / MANIFEST
    pending = json.loads(path.read_text()).get('pending_keys', []) if path.exists() else []
    return key in pending or (key in corrections(root) and key not in recoverable_keys(root))


def apply_corrections(rows, root=ROOT):
    approved = corrections(root)
    citation_path = Path(root) / CITATION_MANIFEST
    citation_guards = ({row['key']: row for row in json.loads(citation_path.read_text()).get('news', [])}
                       if citation_path.exists() else {})
    for row in rows:
        if row.get('key') in approved:
            if row['key'] in citation_guards:
                guard = citation_guards[row['key']]
                current_urls = [source.get('url') for source in row.get('sources', [])]
                replacement_urls = [source['url'] for source in guard['after']['sources']]
                if current_urls not in (guard['source_urls'], replacement_urls):
                    raise ValueError(row['key'] + ': source changed after citation review')
            # A validated later full reading supersedes a temporary access notice.
            if (row.get('key') in recoverable_keys(root) and row.get('has_editorial')
                    and row.get('access_recovery_validated') is True):
                continue
            row.update(copy.deepcopy(approved[row['key']]))
    return rows
