import importlib.util
import hashlib
import zipfile
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
import validate_social_package as validation


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

 def test_carousel_requires_prepared_and_post_save_order(self):
     topics=social.topic_plan(self.items,date(2026,10,26),self.news)
     with tempfile.TemporaryDirectory() as d:
         batch=social.build(topics,{},Path(d),'2026-W43',date(2026,10,19),date(2026,10,25),date(2026,10,26))
         item=next(i for i in batch['items'] if i['platform']=='instagram')
         topic=next(t for t in topics if t['id']==item['topic_id'])
         batch={'topics':[topic],'items':[item]}
         for path in item['prepared_carousel_assets']+item['story']['frames']:
             Path(path).parent.mkdir(parents=True,exist_ok=True)
             Path(path).touch()
         evidence=Path(d,'saved-preview.png')
         evidence.touch()
         record=dict(id=item['id'],status='VERIFIED',caption_verified=True,
             account_verified=True,media_order_verified=True,destination_verified=True,
             media_count=3,media_type='photo_carousel',scheduled_at=item['scheduled_at'],
             evidence=str(evidence),saved_media_order=['cover','explanation','cta'],
             saved_order_checked_after_save=True,saved_order_evidence=str(evidence),
             story_frames_verified=3,story_time_verified=True)
         audit={'items':[record]}
         self.assertEqual(validation.validate(batch,audit),[])
         item['prepared_carousel_assets'][0],item['prepared_carousel_assets'][2]=item['prepared_carousel_assets'][2],item['prepared_carousel_assets'][0]
         self.assertTrue(any('prepared carousel order' in e for e in validation.validate(batch,audit)))
         item['prepared_carousel_assets'][0],item['prepared_carousel_assets'][2]=item['prepared_carousel_assets'][2],item['prepared_carousel_assets'][0]
         record['saved_media_order']=['cta','explanation','cover']
         self.assertTrue(any('saved carousel order' in e for e in validation.validate(batch,audit)))
         record['saved_media_order']=['cover','explanation','cta']
         record['saved_order_checked_after_save']=False
         self.assertTrue(any('checked after save' in e for e in validation.validate(batch,audit)))


class CuratedPhotoReproducibility(unittest.TestCase):
    def test_reviewed_bytes_do_not_depend_on_cdn(self):
        with tempfile.TemporaryDirectory() as d:
            output = Path(d); (output/'sources').mkdir()
            data = b'reviewed photo bytes'
            archive = output/'photos.zip'
            with zipfile.ZipFile(archive,'w') as z: z.writestr('sources/photo.jpg',data)
            photos = {'photo': dict(local_source='sources/photo.jpg',source_url='https://example.org/photo',sha256=hashlib.sha256(data).hexdigest())}
            history = dict(source_urls=[],sha256=[])
            with patch.object(social,'fetch',side_effect=AssertionError('Network must not replace reviewed bytes')):
                social.curated_photos(photos,history,output,archive)
            self.assertEqual((output/'sources/photo.jpg').read_bytes(),data)
            photos['photo']['sha256'] = 'unexpected'
            with self.assertRaisesRegex(ValueError,'archive content changed'):
                social.curated_photos(photos,history,output,archive)

    def test_all_recovery_photos_match_pinned_archive(self):
        config = json.loads((ROOT/'config/social-2026-W43.json').read_text())
        with tempfile.TemporaryDirectory() as d:
            output = Path(d); (output/'sources').mkdir()
            social.curated_photos(config['photos'],dict(source_urls=[],sha256=[]),output,ROOT/'config/social-photos-2026-W43.zip')
            self.assertEqual(len(list((output/'sources').glob('*.jpg'))),14)

if __name__=='__main__':unittest.main()
