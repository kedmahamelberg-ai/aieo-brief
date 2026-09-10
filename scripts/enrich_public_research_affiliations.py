#!/usr/bin/env python3
"""Refresh public research affiliations without invoking an AI model."""
from __future__ import annotations

import json
import os
from pathlib import Path

from research_affiliations import enrich_affiliations

ROOT=Path(__file__).resolve().parents[1]
PATH=ROOT/'data/research/public.json'


def main():
    if not PATH.exists():
        print('No public research file; affiliation refresh skipped.')
        return 0
    data=json.loads(PATH.read_text(encoding='utf-8'))
    papers=data.get('papers') or []
    before=json.dumps(papers,sort_keys=True,ensure_ascii=False)
    status=enrich_affiliations(papers,contact=os.environ.get('RESEARCH_CONTACT_EMAIL',''))
    after=json.dumps(papers,sort_keys=True,ensure_ascii=False)
    counts={name:sum(row['status']==name for row in status) for name in ('matched','not_matched','cached','unavailable')}
    counts['source_verified']=sum(bool(row.get('source_verified')) for row in status)
    if before!=after:
        PATH.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'papers':len(papers),'changed':before!=after,**counts},indent=2))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
