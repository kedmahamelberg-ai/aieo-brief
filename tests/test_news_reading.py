"""News wording must pass readability and then original-source grounding."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import tempfile
from jinja2 import ChoiceLoader, DictLoader, Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import editorial_corrections
import news_reading
from source_evidence_quality import assess_body
from test_editorial_recovery import engine, news, fixture, accepted_review
from validate_public_site import validate_news_layout


class NewsReading(unittest.TestCase):
    def test_chinese_event_ordinal_does_not_hide_a_supported_article(self):
        draft, sources = fixture()
        sources[0]['evidence'] += ' 第十四届论坛呼吁合作。'
        draft['what_happened'] = 'The 14th forum called for cooperation.'
        self.assertEqual(engine.validate_draft(draft, sources)['what_happened'], draft['what_happened'])
        draft['what_happened'] = 'The 15th forum called for cooperation.'
        with self.assertRaises(engine.EditorialError) as caught:
            engine.validate_draft(draft, sources)
        self.assertEqual(caught.exception.code, 'unsupported_number')

    def test_box_only_correction_allows_a_first_summary_but_withholding_stays_locked(self):
        eid='00000000-0000-0000-0000-000000000001'
        release={'evidence':[{'event_id':eid,'event_date':'2026-11-08'}],
                 'complete_content':False,'content_sha256':'edition','release_id':'2026-W45'}
        sym={'evidence':[{'event_id':eid}]}
        source={'source_number':1,'publisher':'Source','headline':'Article','evidence':'Complete source text.'}
        for correction, expected in (({'for_ai':'No AI outcome is described.'},1),
                                     ({'has_editorial':False},0), ({},0)):
            with self.subTest(correction=correction), tempfile.TemporaryDirectory() as folder:
                root=Path(folder)
                with patch.object(news,'ROOT',root), patch.object(news,'corrections',return_value={'event:'+eid:correction}), \
                     patch.object(news,'is_locked',return_value=True), patch.object(news,'fixed_relationship',return_value={'axes':{'evidence_complete':True}}), \
                     patch.object(news,'source_payload',return_value=[source]), patch.object(news,'fingerprint',return_value='input'), \
                     patch.object(news,'version_valid',return_value=False):
                    selected,_,_=news.candidates(release,sym,({}, {}, {},{}))
                self.assertEqual(len(selected),expected)

    def test_all_weekly_pages_put_limits_last_and_hide_internal_status(self):
        archive=json.loads((ROOT/'data/archive/stories.json').read_text())['stories']
        rows=[copy.deepcopy(r) for r in archive if r.get('kind')=='news' and r.get('edition')=='2026-W45']
        editorial_corrections.apply_corrections(rows)
        news_reading.prepare_display(rows)
        env=Environment(loader=ChoiceLoader([DictLoader({
            'base.html':'{% block content %}{% endblock %}',
            'components.html':'{% macro actions(a,b=false) %}{% endmacro %}{% macro ad(a) %}{% endmacro %}',
            'conversation.html':'{% macro conversation(a) %}{% endmacro %}'
        }),FileSystemLoader(str(ROOT/'templates'))]),autoescape=True)
        template=env.get_template('story.html')
        for row in rows:
            with self.subTest(key=row['key']):
                html=template.render(story=row,related=[],local=lambda x:x)
                self.assertNotIn('Evidence incomplete',html)
                self.assertNotIn('Evidence incomplete',(row['human_label'],row['ai_label']))
                validate_news_layout(html)
                if row['event_id'] in ('542e3c89-8ff0-4db5-8976-93960a906859',
                                        '5b24ae60-bccc-48c8-ba54-4996bb4b3f89',
                                        '91aa2239-be4b-40e1-817a-0c4a79792a9f',
                                        '02fa8350-ffe4-4622-bff6-3889ac3c987a'):
                    self.assertTrue(row['has_editorial'])
                    self.assertIn('<h2>What happened</h2>',html)

    def test_display_cleanup_preserves_the_reading_and_internal_direction(self):
        row={'kind':'news','human_direction':'gain','human_label':'Benefits reported',
             'for_humans':'Staff say the tool saves time.', 'ai_direction':'unresolved',
             'ai_label':'Evidence incomplete','for_ai':'The plan proposes wider AI use in public services.'}
        news_reading.prepare_display([row])
        self.assertEqual(row['ai_label'],'')
        self.assertEqual(row['ai_direction'],'unresolved')
        self.assertEqual(row['for_ai'],'The plan proposes wider AI use in public services.')
        self.assertEqual(row['human_label'],'Benefits reported')

    def test_publication_rejects_early_limits_and_status_badges(self):
        for raw in ('<div class="axis-grid"><strong>Evidence incomplete</strong></div>',
                    '<h2>What this does not tell us</h2><div class="axis-grid"><h3>FOR PEOPLE</h3><h3>FOR AI TOOLS AND COMPANIES</h3><summary>Original sources</summary></div>'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                validate_news_layout(raw)

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
