import copy
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from editorial_corrections import apply_corrections,corrections,is_locked
from source_evidence_quality import assess_body
from research_reading import verified_paper_reading
from news_reading import PROSE_INSTRUCTIONS

class ProseFullSourceReview(unittest.TestCase):
    def test_reviewed_syndication_citations_use_exact_first_party_sources(self):
        manifest=json.loads((ROOT/'data/editorial/source-citation-corrections-2026-11-22.json').read_text())
        archive={row['key']:row for row in json.loads((ROOT/'data/archive/stories.json').read_text())['stories']}
        self.assertEqual(len(manifest['news']),30)
        self.assertEqual(len({row['key'] for row in manifest['news']}),30)
        for entry in manifest['news']:
            saved=archive[entry['key']]
            original_urls=[source['url'] for source in saved['sources']]
            replacement=entry['after']
            new_urls=[source['url'] for source in replacement['sources']]
            self.assertIn(original_urls,(entry['source_urls'],new_urls))
            self.assertTrue({'sources','source_count','publisher'} <= set(replacement))
            self.assertTrue(set(replacement) <= {'sources','source_count','publisher','date','display_date','headline','deck','what_happened','body_paragraphs'})
            self.assertEqual(replacement['publisher'],'The Motley Fool')
            self.assertEqual(replacement['source_count'],1)
            self.assertEqual(replacement['sources'][0]['date'],replacement.get('date',saved['date']))
            self.assertTrue(new_urls[0].startswith('https://www.fool.com/'))
            corrected=apply_corrections([copy.deepcopy(saved)])[0]
            for field,value in replacement.items():self.assertEqual(corrected[field],value,(entry['key'],field))
            self.assertNotIn('Globe and Mail',json.dumps(corrected,ensure_ascii=False))
        changed=copy.deepcopy(archive[manifest['news'][0]['key']])
        changed['sources'][0]['url']='https://example.org/different-article'
        with self.assertRaisesRegex(ValueError,'source changed after citation review'):
            apply_corrections([changed])

    def test_later_review_survives_an_earlier_recovery(self):
        audit=json.loads((ROOT/'data/editorial/prose-review-2026-11-17.json').read_text())
        latest=corrections()
        for entry in audit['news']:
            row={'key':entry['key'],'access_recovery_validated':True,'has_editorial':True,**copy.deepcopy(entry['before'])}
            apply_corrections([row])
            for field in entry['after']:self.assertEqual(row[field],latest[entry['key']][field],(entry['key'],field))
            self.assertTrue(is_locked(row['key']))
        self.assertEqual(latest['event:e9a9b601-601d-470b-9dcb-d95e51a0b2f3']['source_replacement_note'],'')
        health=next(r for r in audit['news'] if r['key']=='event:1000c6be-1e4b-487d-a990-7d87fe76533c')
        self.assertNotIn('does not report what happened',health['after']['why_it_matters'])
        self.assertEqual(health['after']['limitation'],'')

    def test_partial_source_labels_cannot_pass_on_length(self):
        body='A long introduction is still an introduction rather than the complete source. '*100
        for basis in ('abstract_only','chart_captions','video_introduction','video_caption_only'):
            self.assertFalse(assess_body({'body_text':body,'content_basis':basis})['usable_complete_body'])
        self.assertTrue(assess_body({'body_text':body,'content_basis':'full_source'})['usable_complete_body'])

    def test_recovered_paper_has_version_bound_full_text_proof(self):
        audit=json.loads((ROOT/'data/editorial/prose-review-2026-11-17.json').read_text())
        row=next(r for r in audit['research'] if r['key']=='paper:29f3a0ced2bcb71a33818a12')['after']
        self.assertTrue(verified_paper_reading({**row,'arxiv_id':'2611.18553v1'}))
        self.assertFalse(verified_paper_reading({**row,'arxiv_id':'2611.18553v2'}))
        self.assertIn('Do not repeat the same caveat',PROSE_INSTRUCTIONS)
