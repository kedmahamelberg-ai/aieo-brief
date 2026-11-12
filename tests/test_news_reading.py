"""News wording must pass readability and then original-source grounding."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import editorial_corrections
import news_reading
from source_evidence_quality import assess_body
from test_editorial_recovery import engine, fixture, accepted_review


class NewsReading(unittest.TestCase):
    def test_news_rewrite_is_followed_by_full_source_review(self):
        good, sources = fixture()
        bad = copy.deepcopy(good)
        bad['for_humans'] = 'Governance improves operational capabilities at scale.'
        public = {k: copy.deepcopy(good[k]) for k in good if k != 'support'}
        with patch.object(engine, 'call_json', side_effect=[bad, public, accepted_review()]) as model:
            result, _ = engine.write_story({}, {}, sources)
        self.assertEqual(result['for_humans'], good['for_humans'])
        self.assertEqual([c.kwargs['stage'] for c in model.call_args_list],
                         ['draft', 'reading_level', 'scope_review'])
        self.assertIn(sources[0]['evidence'][:42], model.call_args_list[-1].args[0])

    def test_review_rejects_unexplained_language_even_when_facts_pass(self):
        draft, sources = fixture()
        for value in (False, None):
            review = accepted_review()
            if value is None:
                review.pop('plain_english')
            else:
                review['plain_english'] = value
            with self.subTest(value=value), patch.object(engine, 'call_json', return_value=review):
                with self.assertRaises(engine.EditorialError):
                    engine.review_scope(draft, sources)

    def test_news_gate_rejects_meta_copy_jargon_and_dense_sentences(self):
        for value in ('This explains the topic in plain terms.',
                      'AI operators gain deployment capabilities.',
                      'People ' + 'often ' * 28 + 'benefit.'):
            with self.subTest(value=value):
                self.assertTrue(news_reading.style_problem({'for_humans': value}))
        self.assertFalse(news_reading.style_problem({'for_humans': '', 'for_ai': ''}))

    def test_readable_edit_still_fails_if_meaning_changes(self):
        good, sources = fixture()
        bad = copy.deepcopy(good)
        bad['for_humans'] = 'Governance matters.'
        changed = {k: copy.deepcopy(good[k]) for k in good if k != 'support'}
        changed['for_humans'] = 'AI makes every musician rich.'
        review = accepted_review(changed)
        review.update(no_unstated_effects=False, reason='Invented benefit for all musicians.')
        with patch.object(engine, 'call_json', side_effect=[copy.deepcopy(bad), changed, review] * 3):
            with self.assertRaises(engine.EditorialError):
                engine.write_story({}, {}, sources)

    def test_every_current_edition_story_has_both_reviewed_boxes(self):
        archive = json.loads((ROOT / 'data/archive/stories.json').read_text())['stories']
        current = {r['key'] for r in archive if r.get('kind') == 'news' and r.get('edition') == '2026-W45'}
        audit = json.loads((ROOT / 'data/editorial/plain-language-corrections-2026-11-12.json').read_text())
        self.assertEqual({r['key'] for r in audit['news']}, current)
        self.assertEqual(len(audit['news']), 74)
        for row in audit['news']:
            with self.subTest(key=row['key']):
                self.assertTrue(row['after']['for_humans'])
                self.assertTrue(row['after']['for_ai'])
                self.assertFalse(news_reading.style_problem(row['after']))
                self.assertTrue(row['retained_source_sha256'])
                self.assertTrue(editorial_corrections.is_locked(row['key']))
                if row['reading_scope'] == 'full_article_unavailable':
                    self.assertFalse(row['after']['has_editorial'])
                    self.assertFalse(row['after']['body_paragraphs'])
                    self.assertFalse(row['after']['evidence_complete'])

    def test_access_gates_and_navigation_cannot_pass_as_complete_articles(self):
        cases = ['La suite de cet article est réservée à nos abonnés. ' * 4,
                 '正文\n更多内容请看：\n全文｜报告 ' * 4,
                 '当前位置：首页>正文\nProduced By CMS ' * 4,
                 '相关链接：\n' + '\n'.join('- 政府部门' for _ in range(25))]
        for text in cases:
            with self.subTest(text=text):
                self.assertFalse(assess_body({'body_text': text, 'content_basis': 'full_source'})['usable_complete_body'])
        notice = 'The library invites students to discuss artificial intelligence on Wednesday. The notice gives the time, venue and entry requirements.'
        self.assertTrue(assess_body({'body_text': notice, 'content_basis': 'full_source'})['usable_complete_body'])


if __name__ == '__main__':
    unittest.main()
