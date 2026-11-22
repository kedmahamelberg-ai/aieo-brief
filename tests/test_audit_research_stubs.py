import sys
import unittest
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from audit_research_stubs import source_ready_stubs
from research_reading import verified_paper_reading


class ResearchStubAuditTests(unittest.TestCase):
    def test_source_reviewed_replacements_have_identifiable_full_paper_proof(self):
        root = Path(__file__).resolve().parents[1]
        manifest = json.loads((root / 'data/editorial/research-stub-corrections-2026-11-22.json').read_text())
        records = {item['key']: item for item in json.loads((root / 'data/research/public.json').read_text())['papers']}
        self.assertEqual(len(manifest['research']), 10)
        for item in manifest['research']:
            with self.subTest(key=item['key']):
                row = records[item['key']]
                self.assertTrue(row['has_editorial'])
                self.assertEqual(row['paper_source_url'], item['source_urls'][0])
                self.assertTrue(verified_paper_reading(row))

    def test_accessible_full_paper_is_a_failure_without_retrying_a_model(self):
        papers = [{'key': 'paper:one', 'arxiv_id': '2611.23221v1', 'has_editorial': False},
                  {'key': 'paper:two', 'arxiv_id': '2611.24936v1', 'has_editorial': True}]
        calls = []
        def read(paper):
            calls.append(paper['key'])
            return {'status': 'read', 'url': 'https://arxiv.org/html/' + paper['arxiv_id']}
        result = source_ready_stubs(papers, read)
        self.assertEqual(calls, ['paper:one'])
        self.assertEqual(result[0]['key'], 'paper:one')

    def test_inaccessible_full_paper_remains_withheld(self):
        paper = {'key': 'paper:one', 'arxiv_id': '2611.23221v1', 'has_editorial': False}
        self.assertEqual(source_ready_stubs([paper], lambda _: {'status': 'pdf_unavailable'}), [])
