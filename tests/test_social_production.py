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
 return dict(kind='news',edition='2026-W43',period_start='2026-10-19',period_end='2026-10-25',date='2026-10-24',markets=[market],path=f'story/{market.lower()}-{number}/index.html',headline='A useful AI development in '+social.COUNTRIES[market],deck='A source-backed introduction',what_happened='Researchers reported a finding in a specific study.',body_paragraphs=['Evidence and context.'],sources=[{'url':'https://example.org/source'}],has_editorial=True)


class SocialProduction(unittest.TestCase):
 def test_photo_freshness_uses_permanent_history_not_the_news_week(self):
  page={'title':'File:Washington policy building.jpg','imageinfo':[{'extmetadata':{
      'DateTimeOriginal':{'value':'2015-03-26 18:03:17'},
      'ImageDescription':{'value':'A camera photograph of a policy building.'},
  }}]}
  self.assertEqual(social.verified_camera_date(page,'2026-W46'),'2015-03-26')
  page['imageinfo'][0]['extmetadata']['DateTimeOriginal']['value']='2099-01-01'
  self.assertIsNone(social.verified_camera_date(page,'2026-W46'))
  page['imageinfo'][0]['extmetadata']['DateTimeOriginal']['value']='2015-03-26'
  page['imageinfo'][0]['extmetadata']['ImageDescription']['value']='AI-generated illustration'
  self.assertIsNone(social.verified_camera_date(page,'2026-W46'))
 def test_scanned_photo_cannot_use_a_conflicting_exif_year_as_capture_date(self):
  page={'title':'File:Luftbild New York City, 1995.jpg','imageinfo':[{'extmetadata':{
      'DateTimeOriginal':{'value':'2024-11-27'},
      'ImageDescription':{'value':'An aerial photograph of New York City.'},
  }}]}
  self.assertIsNone(social.verified_camera_date(page,'2026-W47'))
  page['imageinfo'][0]['extmetadata']['DateTimeOriginal']['value']='1995-06-01'
  self.assertEqual(social.verified_camera_date(page,'2026-W47'),'1995-06-01')
 def test_discovery_market_cannot_turn_dutch_news_into_uk_news(self):
  row=news('GB',1);row.update(headline='Dutch lawmakers propose rules for school AI',what_happened='The Dutch parliament discusses a proposal for primary schools.')
  self.assertEqual(social.verified_markets(row),[])
 def test_us_essay_is_not_uk_news_and_nhs_is_uk_news(self):
  row=news('GB',1);row.update(headline='A literary critic discusses AI and dignity',what_happened='An essay compares generative AI with horror.')
  self.assertEqual(social.verified_markets(row),[])
  row.update(headline='NHS Highland tests MRI referral support')
  self.assertEqual(social.verified_markets(row),['GB'])
 def setUp(self):
  directory=tempfile.TemporaryDirectory();self.addCleanup(directory.cleanup)
  original=social.completed_week
  completion=patch.object(social,"completed_week",side_effect=lambda root,week,state=None: original(Path(directory.name),week,state))
  completion.start();self.addCleanup(completion.stop)
  self.news=[news(m,n) for m in social.COUNTRIES for n in range(4)]
  self.items=self.news+[dict(kind='research',date='2026-10-22',path='research/one/index.html',headline='A research result',deck='A research question',what_happened='An abstract describes the findings.',sources=[{'url':'https://example.org/paper'}],research_label='Preprint',summary_basis='Summary of the abstract')]
 def test_coverage_not_release_number_determines_publication_week(self):
  self.assertEqual(social.edition(self.items)[3],date(2026,10,26))
  self.assertEqual(social.due(self.items,{},date(2026,10,26)),(True,'2026-W43'))
 def test_completed_edition_is_idempotent_even_after_culture_refresh(self):
  self.assertFalse(social.due(self.items+[dict(kind='culture',date='2026-10-27')],{'editions':{'2026-W43':{}}},date(2026,10,27))[0])
 def test_social_waits_for_fourteen_completed_source_backed_stories(self):
  monday=date(2026,10,26)
  self.assertEqual(social.social_source_readiness(self.items,monday,self.news,'2026-W43'),(20,True))
  incomplete=[dict(row,has_editorial=False) for row in self.news[:7]]+self.news[7:]
  self.assertEqual(social.social_source_readiness(incomplete+self.items[20:],monday,incomplete,'2026-W43'),(13,True))
 def test_w45_review_revision_replaces_image_risk_without_repeating_later_weeks(self):
  rows=[dict(row,edition='2026-W45',period_start='2026-11-02',period_end='2026-11-08') for row in self.items]
  self.assertTrue(social.due(rows,{'editions':{'2026-W45':{}}},date(2026,11,9))[0])
  self.assertTrue(social.due(rows,{'editions':{'2026-W45':{'review_revision':2}}},date(2026,11,9))[0])
  self.assertTrue(social.due(rows,{'editions':{'2026-W45':{'review_revision':3}}},date(2026,11,9))[0])
  self.assertFalse(social.due(rows,{'editions':{'2026-W45':{'review_revision':4}}},date(2026,11,9))[0])
 def test_old_and_unfinished_editions_cannot_be_new_content(self):
  self.assertFalse(social.due(self.items,{},date(2026,11,2))[0])
  with self.assertRaises(ValueError):social.due(self.items,{},date(2026,10,25))
 def test_missing_market_uses_general_news_without_false_country(self):
  filtered=[i for i in self.news if i['markets']!=['GB']]
  topics=social.topic_plan(self.items,date(2026,10,26),filtered)
  self.assertEqual(len([t for t in topics if t['kind']=='News']),14)
  self.assertFalse(any(t['market']=='GB' for t in topics))
  self.assertTrue(any(t['market']=='GLOBAL' and not t['country'] for t in topics))
 def test_w45_source_audit_excludes_future_event_and_identified_editorial(self):
  archive=json.loads((ROOT/'data/archive/stories.json').read_text())['stories']
  current=[row for row in archive if row.get('kind')=='news' and row.get('edition')=='2026-W45']
  for row in current:
   if row['slug']=='cranky-don-joe-questions-ai-s-feel-risk':row['claim_status']='opinion'
  source_read=social.read
  def archive_read(path,default=None):
   value=source_read(path,default)
   return {key:row for key,row in value.items() if key!='selected_news'} if path.name=='social-source-audit-2026-W45.json' else value
  with patch.object(social,'read',side_effect=archive_read):
   topics=social.topic_plan(archive,date(2026,11,9),current)
  paths={topic['path'] for topic in topics}
  self.assertEqual(len(topics),15)
  self.assertFalse(any('animation-generative-ai-creator' in path or 'cranky-don-joe' in path or 'ai-bubble-faces-reality' in path for path in paths))
  paper=next(topic for topic in topics if topic['kind']=='Research')
  self.assertIn('153 reconstructed website environments',paper['fact'])
  self.assertNotIn('performed best',paper['fact'])
  medical=next(topic for topic in topics if 'ultrasound' in topic['path'])
  self.assertEqual(medical['second_subject_tag'],'#HealthAI')
  scopes=json.loads((ROOT/'config/social-photo-scopes-2026-W45.json').read_text())
  self.assertGreaterEqual(len(scopes['topics']),14)
  audit=json.loads((ROOT/'config/social-source-audit-2026-W45.json').read_text())
  self.assertEqual(len(audit['selected_news']),14)
  self.assertTrue(set(audit['selected_news']).issubset(scopes['topics']))
  self.assertTrue(all((scope.get('queries') or scope.get('preferred_files')) and scope['title_pattern'] and scope['kind'] in ('place','subject') for scope in scopes['topics'].values()))
 def test_complete_schedule_and_media_contract(self):
  topics=social.topic_plan(self.items,date(2026,10,26),self.news)
  self.assertEqual(len(topics),15);self.assertEqual(len({t['path'] for t in topics}),15)
  for market in social.COUNTRIES:self.assertIn(sum(t['market']==market for t in topics),(2,3))
  with tempfile.TemporaryDirectory() as d:
   batch=social.build(topics,{},Path(d),'2026-W43',date(2026,10,19),date(2026,10,25),date(2026,10,26))
  self.assertEqual(len(batch['items']),60)
  self.assertEqual(batch['status'],social.STATUS)
  self.assertIn('research/one/index.html',batch['substack_post']['body'])
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
         card_evidence=[Path(d,f'saved-card-{n}.png') for n in (1,2,3)]
         for path in card_evidence:path.touch()
         record=dict(id=item['id'],status='VERIFIED',caption_verified=True,
             account_verified=True,media_order_verified=True,destination_verified=True,
             media_count=3,media_type='photo_carousel',scheduled_at=item['scheduled_at'],
             evidence=str(evidence),saved_media_order=['cover','explanation','cta'],
             saved_order_checked_after_save=True,saved_order_evidence=[str(p) for p in card_evidence],
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
         record['saved_order_checked_after_save']=True
         record['saved_order_evidence']=[str(card_evidence[0])]*3
         self.assertTrue(any('three distinct' in e for e in validation.validate(batch,audit)))


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


class AutomaticPhotoSourcing(unittest.TestCase):
    def page(self, title, *, license='CC0', description='New York city skyline, United States', captured='2024-01-19', width=1800):
        return {'title': 'File:'+title, 'imageinfo': [{
            'mime': 'image/jpeg', 'width': width, 'height': 1200,
            'descriptionurl': 'https://commons.wikimedia.org/wiki/File:'+title,
            'url': 'https://upload.wikimedia.org/'+title,
            'extmetadata': {'LicenseShortName': {'value': license},
                            'DateTimeOriginal': {'value': captured},
                            'ImageDescription': {'value': description}},
        }]}

    def run_search(self, root, pages, topics, history=None):
        output = root/'output'; (output/'sources').mkdir(parents=True)
        queries = []
        def fetch(url, target=None):
            if target is not None:
                target.write_bytes(url.encode())
                return
            queries.append(url)
            return json.dumps({'query': {'pages': {str(i): page for i, page in enumerate(pages)}}}).encode()
        with patch.object(social, 'ROOT', root), patch.object(social, 'fetch', side_effect=fetch):
            photos = social.new_photos(topics, history or {'source_urls': [], 'sha256': []}, output, '2026-W47')
        return photos, queries, output

    def test_named_city_photos_pass_without_literal_country_in_filename(self):
        topics = [{'id': 'first', 'kind': 'News', 'market': 'US', 'path': 'story/one/'},
                  {'id': 'second', 'kind': 'News', 'market': 'US', 'path': 'story/two/'}]
        pages = [self.page('New York Midtown skyline.jpg'), self.page('Manhattan river skyline.jpg')]
        with tempfile.TemporaryDirectory() as d:
            photos, queries, _ = self.run_search(Path(d), pages, topics)
        self.assertEqual(len(photos), 2)
        self.assertEqual(len(queries), 1)  # Reuse metadata while rejecting already-selected photographs.
        from urllib.parse import parse_qs, urlparse
        self.assertIn('incategory:CC-Zero', parse_qs(urlparse(queries[0]).query)['gsrsearch'][0])

    def test_fallback_preserves_rights_location_date_size_and_duplicate_gates(self):
        used = self.page('New York used skyline.jpg')
        repeated_bytes = self.page('New York duplicate skyline.jpg')
        rejected = [used, repeated_bytes,
                    self.page('New York restricted skyline.jpg', license='CC BY-SA 4.0'),
                    self.page('Paris skyline.jpg', description='Paris city, France'),
                    self.page('New York future skyline.jpg', captured='2099-01-01'),
                    self.page('New York undated skyline.jpg', captured=''),
                    self.page('New York tiny skyline.jpg', width=500),
                    self.page('New York synthetic skyline.jpg', description='AI-generated New York skyline')]
        good = self.page('New York Brooklyn skyline.jpg')
        history = {'source_urls': [used['imageinfo'][0]['descriptionurl']],
                   'sha256': [hashlib.sha256(repeated_bytes['imageinfo'][0]['url'].encode()).hexdigest()]}
        with tempfile.TemporaryDirectory() as d:
            photos, _, _ = self.run_search(Path(d), rejected+[good],
                [{'id': 'first', 'kind': 'News', 'market': 'US', 'path': 'story/one/'}], history)
        self.assertEqual(photos['first']['source_url'], good['imageinfo'][0]['descriptionurl'])

    def test_failed_search_keeps_diagnostics_and_never_marks_a_partial_package_ready(self):
        topics = [{'id': 'first', 'kind': 'News', 'market': 'US', 'path': 'story/one/'},
                  {'id': 'second', 'kind': 'News', 'market': 'US', 'path': 'story/two/'}]
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            with self.assertRaisesRegex(ValueError, 'second'):
                self.run_search(root, [self.page('New York river skyline.jpg')], topics)
            output = root/'output'
            self.assertEqual(len(json.loads((output/'PHOTO_MANIFEST.json').read_text())), 1)
            report = json.loads((output/'PHOTO_SELECTION_REPORT.json').read_text())
            self.assertEqual(report['failed_topic'], 'second')
            self.assertEqual(report['selected_photos'], 1)
            self.assertFalse((output/'READY_FOR_REVIEW.json').exists())

    def test_explicit_story_photo_scope_is_not_replaced_by_default_city_search(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); scope = root/'config/social-photo-scopes-2026-W47.json'
            scope.parent.mkdir()
            scope.write_text(json.dumps({'schema_version': 'brief_social_photo_scopes_v1',
                'source_edition': '2026-W47', 'topics': {'story/one/': {
                    'queries': ['Capitol building'], 'title_pattern': 'Capitol', 'kind': 'place'}}}))
            with self.assertRaisesRegex(ValueError, 'first'):
                self.run_search(root, [self.page('New York river skyline.jpg')],
                    [{'id': 'first', 'kind': 'News', 'market': 'US', 'path': 'story/one/'}])

if __name__=='__main__':unittest.main()
