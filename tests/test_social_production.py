import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import prepare_social_review as social


def news(market,number):
 return dict(kind='news',edition='2026-W43',period_start='2026-10-19',period_end='2026-10-25',date='2026-10-24',markets=[market],path=f'story/{market.lower()}-{number}/index.html',headline='A useful AI development',deck='A source-backed introduction',what_happened='Researchers reported a finding in a specific study.',body_paragraphs=['Evidence and context.'],sources=[{'url':'https://example.org/source'}],has_editorial=True)


class SocialProduction(unittest.TestCase):
 def setUp(self):
  self.news=[news(m,n) for m in social.COUNTRIES for n in range(4)]
  self.items=self.news+[dict(kind='research',date='2026-10-22',path='research/one/index.html',headline='A research result',deck='A research question',what_happened='An abstract describes the findings.',sources=[{'url':'https://example.org/paper'}],research_label='Preprint',summary_basis='Summary of the abstract')]
 def test_coverage_not_release_number_determines_publication_week(self):
  self.assertEqual(social.edition(self.items)[3],date(2026,10,26))
  self.assertEqual(social.due(self.items,{},date(2026,10,26)),(True,'2026-W43'))
 def test_completed_edition_is_idempotent_even_after_culture_refresh(self):
  self.assertFalse(social.due(self.items+[dict(kind='culture',date='2026-10-27')],{'editions':{'2026-W43':{}}},date(2026,10,27))[0])
 def test_old_and_unfinished_editions_cannot_be_new_content(self):
  self.assertFalse(social.due(self.items,{},date(2026,11,2))[0])
  with self.assertRaises(ValueError):social.due(self.items,{},date(2026,10,25))
 def test_missing_market_blocks_instead_of_substitution(self):
  filtered=[i for i in self.news if i['markets']!=['GB']]
  with self.assertRaises(ValueError):social.topic_plan(self.items,date(2026,10,26),filtered)
 def test_complete_schedule_and_media_contract(self):
  topics=social.topic_plan(self.items,date(2026,10,26),self.news)
  self.assertEqual(len(topics),15);self.assertEqual(len({t['path'] for t in topics}),15)
  for market in social.COUNTRIES:self.assertIn(sum(t['market']==market for t in topics),(2,3))
  with tempfile.TemporaryDirectory() as d:
   batch=social.build(topics,{},Path(d),'2026-W43',date(2026,10,19),date(2026,10,25),date(2026,10,26))
  self.assertEqual(len(batch['items']),60)
  self.assertEqual(batch['status'],social.STATUS)
  for i in batch['items']:
   self.assertTrue(i['scheduled_at'].endswith('+01:00'))
   self.assertEqual(len(i['prepared_carousel_assets']),3 if i['platform'] in ['facebook','instagram'] else 1)
   if i['platform']=='instagram':
    self.assertEqual(i['story']['scheduled_at'],i['scheduled_at']);self.assertFalse(i['story']['link_stickers_enabled'])
    self.assertTrue(i['prepared_carousel_assets'][0].endswith('_carousel_1.png'));self.assertNotIn('https://',i['caption'])
 def test_failed_or_partial_package_cannot_record_a_receipt(self):
  with tempfile.TemporaryDirectory() as d,patch.object(sys,'argv',['prepare_social_review.py','--record','--output',d]):
   Path(d,'batch.json').write_text('{}')
   with self.assertRaises(AssertionError):social.main()
 def test_deploy_dependency_not_clock_or_workflow_run(self):
  build=(ROOT/'.github/workflows/build-brief-preview.yml').read_text();trigger=(ROOT/'.github/workflows/prepare-social-review.yml').read_text()
  self.assertIn('needs: deploy',build);self.assertIn("if: needs.deploy.result == 'success'",build)
  self.assertNotIn('cron:',trigger);self.assertNotIn('workflow_run:',trigger)
  self.assertNotIn('OPENAI_API_KEY',trigger);self.assertNotIn('SOCIAL_ACCESS_TOKEN',trigger)

if __name__=='__main__':unittest.main()
