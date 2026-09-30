"""Research repair must retain evidence checks and the full published backlog."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import research_recovery as recovery
import editorial_engine as engine
from generate_research_summaries import merge_recent


class ResearchRecovery(unittest.TestCase):
    def test_quote_choices_are_exact_bounded_passages(self):
        evidence = 'An exact sentence about the experiment. ' + 'Long evidence phrase ' * 80
        sources = [{'source_number': 1, 'evidence': evidence}]
        schema = engine.draft_schema(sources, 'preprint')
        quotes = schema['properties']['support']['items']['properties']['quote']['enum']
        self.assertTrue(quotes)
        for quote in quotes:
            self.assertTrue(12 <= len(quote) <= 400)
            self.assertIn(quote, engine.normalized(evidence))
        self.assertNotIn('enum', engine.draft_schema(sources, 'news')['properties']['support']['items']['properties']['quote'])

    def paper(self):
        return {'key': 'paper:one', 'arxiv_id': '2609.35767v1', 'original_headline': 'Study title',
                'date': '2026-08-01', 'has_editorial': False}

    def test_exact_version_html_recovers_only_the_abstract(self):
        html = '<meta name="citation_title" content="Study title"><blockquote class="abstract mathjax"><span>Abstract:</span> Researchers test whether a model can revise its images. The reported tests compare their method with a baseline.</blockquote><p>Navigation must stay out.</p>'
        get = Mock(return_value=Mock(text=html))
        result = recovery.recover(self.paper(), get)
        get.assert_called_once_with('https://arxiv.org/abs/2609.35767v1')
        self.assertNotIn('Navigation', result['abstract'])
        self.assertNotIn('Abstract:', result['abstract'])
        self.assertEqual(result['pdf_url'], 'https://arxiv.org/pdf/2609.35767v1')
        get.return_value.text = html.replace('Study title', 'Unrelated paper')
        self.assertIsNone(recovery.recover(self.paper(), get))

    def test_archive_backlog_survives_discovery_and_network_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'data/archive').mkdir(parents=True)
            (root / 'data/research').mkdir()
            paper = self.paper()
            (root / 'data/archive/stories.json').write_text(json.dumps({'stories': [paper]}))
            (root / 'data/research/public.json').write_text(json.dumps({'papers': []}))
            with patch.object(recovery, 'recover', return_value={**paper, 'abstract': 'Retained evidence'}), patch.object(recovery.time, 'sleep'):
                rows, status = recovery.recover_unfinished(root, [], Mock())
            self.assertEqual(rows[0]['key'], paper['key'])
            self.assertEqual(status['recovered'], 1)
            with patch.object(recovery, 'recover', side_effect=recovery.requests.Timeout), patch.object(recovery.time, 'sleep'):
                rows, status = recovery.recover_unfinished(root, [], Mock())
            self.assertEqual(rows, [paper])
            self.assertEqual(status['unavailable'], 1)
            (root / 'data/research/public.json').write_text(json.dumps({'papers': [{**paper, 'has_editorial': True}]}))
            self.assertEqual(recovery.unfinished(root), [])

    def test_repaired_old_paper_reaches_archive_build(self):
        paper = {**self.paper(), 'has_editorial': True}
        self.assertIn(paper, merge_recent({}, [paper], '2026-09-30'))

if __name__ == '__main__':
    unittest.main()
