import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import editorial_corrections as corrections
import prepare_social_review as social


class SourceAuditCorrections(unittest.TestCase):
    def test_country_photo_filter_rejects_the_known_misleading_subjects(self):
        def page(title, description=''):
            return {'title': 'File:'+title, 'imageinfo': [{'extmetadata': {'ImageDescription': {'value': description}}}]}
        self.assertFalse(social.country_scene_candidate(page('Canada Saskatchewan wildfires.jpg'), 'CA'))
        self.assertFalse(social.country_scene_candidate(page('Fengge by the riverside in Shanghai.jpg', 'Portrait of a man'), 'CN'))
        self.assertFalse(social.country_scene_candidate(page('Amsterdam city skyline.jpg'), 'GB'))
        self.assertFalse(social.country_scene_candidate(page('Shanghai painting.jpg'), 'CN'))
        self.assertTrue(social.country_scene_candidate(page('Canada winter landscape.jpg'), 'CA'))
        self.assertTrue(social.country_scene_candidate(page('Shanghai Skyline1.jpg'), 'CN'))

    def test_w46_completion_keeps_complete_copy_and_repairs_missing_pages(self):
        audit=json.loads((ROOT/'data/editorial/w46-completion-corrections-2026-11-16.json').read_text())
        keys=[r['key'] for r in audit['news']]
        self.assertEqual(len(keys),67)
        import news_reading
        for entry in audit['news']:
            after=entry['after']
            self.assertTrue(after['location_label'])
            self.assertTrue(entry['geography_review'])
            self.assertTrue(after['for_humans'])
            self.assertTrue(after['for_ai'])
            self.assertFalse(news_reading.style_problem(after))
            news_reading.validate_effects(after['box_effects'],after)
            self.assertEqual(after['human_direction'],after['box_effects']['human'])
            self.assertEqual(after['ai_direction'],after['box_effects']['ai'])
        self.assertEqual(len(keys),len(set(keys)))
        reviewed={r['key']:r['after'] for r in audit['news']}
        self.assertEqual(reviewed['event:87ee4ebb-3ad2-4728-9656-1c430d0b2f4d']['location_label'],'Commentary')
        self.assertEqual(reviewed['event:a8cdc3a3-07f2-4018-88ed-53fa68ead705']['location_label'],'Japan')
        self.assertEqual(reviewed['event:81d30770-8588-4aac-88a2-6463131a6862']['location_label'],'Research locations: Brazil · USA')
        existing={'key':'event:already-complete-unrelated','headline':'Preserve this','has_editorial':True,'body_paragraphs':['Original complete text.']}
        full_keys=[r['key'] for r in audit['news'] if r['after'].get('has_editorial')]
        rows=[{'key':key,'has_editorial':False,'body_paragraphs':[]} for key in full_keys]+[copy.deepcopy(existing)]
        corrections.apply_corrections(rows)
        for row in rows[:-1]:
            self.assertTrue(row['has_editorial'])
            self.assertTrue(all(row.get(k) for k in ('headline','deck','what_happened','why_it_matters','body_paragraphs')))
            self.assertTrue(corrections.is_locked(row['key']))
        self.assertEqual(rows[-1],existing)
        venue=next(r for r in rows if r['key']=='event:76b0b3fe-5908-4c17-b875-e6e27d5b23a8')
        self.assertIn('57 avenue de Montjoux',' '.join(venue['body_paragraphs']))
        self.assertNotIn('no venue',venue['headline'])
        chart=next(r for r in rows if r['key']=='event:e9a9b601-601d-470b-9dcb-d95e51a0b2f3')
        self.assertEqual(chart['source_reading_scope'],'full_article')
        self.assertEqual(chart['sources'][0]['publisher'],'Kiplinger / Kevin Webb')
        self.assertEqual(chart['box_effects'],{'human':'loss','ai':'loss'})
        before=copy.deepcopy(rows)
        corrections.apply_corrections(rows)
        self.assertEqual(rows,before)

    def test_registered_audit_repairs_content_without_changing_other_articles(self):
        audit = json.loads((ROOT/corrections.SOURCE_AUDITS[0]).read_text())
        rows = [{'key': row['key'], **copy.deepcopy(row['before'])} for row in audit['news']+audit['research']]
        unrelated = {'key': 'unrelated', 'headline': 'Keep original'}
        rows.append(unrelated)
        corrections.apply_corrections(rows)
        for actual, expected in zip(rows, audit['news']+audit['research']):
            for field, value in expected['after'].items():
                self.assertEqual(actual[field], value)
        self.assertEqual(rows[-1], unrelated)

    def test_country_proof_becomes_invalid_when_article_changes(self):
        row = dict(key='tested', headline='NHS Highland', sources=[{'url':'https://source.example'}])
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root/'config').mkdir()
            (root/'config/social-geography.json').write_text(json.dumps({'articles': {'tested': {'markets':['GB'], 'content_sha256':social.geography_fingerprint(row)}}}))
            with patch.object(social, 'ROOT', root):
                self.assertEqual(social.verified_markets(row), ['GB'])
                row['headline'] = 'A changed story'
                with self.assertRaisesRegex(ValueError, 'stale'):
                    social.verified_markets(row)
