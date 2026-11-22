#!/usr/bin/env python3
"""Fail a research run when an accessible full paper remains a title-only page.

This check reads only original paper files. It never dispatches a model or
turns an unverified draft into public copy.
"""
import json
from pathlib import Path
from research_reading import read_paper

ROOT = Path(__file__).resolve().parents[1]


def source_ready_stubs(papers, reader=read_paper):
    failures = []
    for paper in papers:
        if paper.get('has_editorial') or not paper.get('arxiv_id'):
            continue
        reading = reader(paper)
        if reading.get('status') == 'read':
            failures.append({'key': paper['key'], 'source': reading['url']})
    return failures


def main():
    papers = json.loads((ROOT / 'data/research/public.json').read_text())['papers']
    failures = source_ready_stubs(papers)
    for item in failures:
        print(f"::error::Full original paper is accessible, but {item['key']} remains a title-only page: {item['source']}")
    if failures:
        raise SystemExit(1)
    print('No accessible full-paper research stubs found.')


if __name__ == '__main__':
    main()
