import contextlib,copy,io,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,Mock
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import collect_daily_culture as culture
from generate_research_summaries import merge_recent
from brief_contract import load_config

class DailyPublication(unittest.TestCase):
 def item(self,kind):
  return culture.record(kind,kind,'A work','A creator','https://example.test/work','A source',{'url':'https://creativecommons.org/publicdomain/zero/1.0/','label':'CC0'},work_date='1854',excerpt='A sentence with an original and traceable source.')
 def test_research_provider_failure_does_not_erase_recent_papers(self):
  old={r['key']:r for r in [{'key':'pnas','date':'2026-09-01'},{'key':'ssrn','date':'2026-08-30'},{'key':'older','date':'2026-07-01'}]}
  result=merge_recent(old,[{'key':'arxiv','date':'2026-09-06'}],'2026-09-06')
  self.assertEqual({x['key'] for x in result},{'pnas','ssrn','arxiv'})
 def test_changed_paper_metadata_replaces_outdated_summary(self):
  old={'one':{'key':'one','date':'2026-09-01','has_editorial':True,'headline':'Earlier claim'}}
  current={'key':'one','date':'2026-09-01','has_editorial':False,'headline':'Corrected paper title'}
  self.assertEqual(merge_recent(old,[current],'2026-09-06'),[current])
 def test_reuse_gate_rejects_noncommercial_and_unknown_licences(self):
  self.assertIsNone(culture.licence('https://creativecommons.org/licenses/by-nc/4.0/'))
  self.assertIsNone(culture.licence('All rights reserved'))
  self.assertEqual(culture.licence('http://creativecommons.org/licenses/by/3.0/')['label'],'CC BY 3.0')
 def test_quote_is_complete_and_not_a_cut_off_dialogue(self):
  text='The garden is full of the sound of birds. “Come with me into the garden!'
  self.assertEqual(culture.quotable_sentences(text),['The garden is full of the sound of birds.'])
 def test_missing_book_heading_cannot_attribute_preface_to_author(self):
  raw='*** START OF THE PROJECT GUTENBERG EBOOK ***\n'+('This is an introduction by someone else. '*20)
  with self.assertRaises(ValueError):culture.passages(raw,'The first chapter')
 def test_partial_day_keeps_valid_work_and_retries_only_missing_type(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'config').mkdir();(root/'config/culture.json').write_text(json.dumps({'enabled':True,'retention_days':45}))
   art=self.item('illustration');poem=self.item('poetry');text=self.item('text');quote=self.item('quote');music=self.item('music')
   with patch.object(culture,'ROOT',root),patch.object(sys,'argv',['collect_daily_culture.py','--date','2026-09-06']),patch.dict('os.environ',{},clear=True),contextlib.redirect_stdout(io.StringIO()):
    with patch.object(culture,'illustration',return_value=art),patch.object(culture,'poetry',side_effect=ValueError('source offline')),patch.object(culture,'literature',return_value=(text,quote)),patch.object(culture,'music',return_value=music):
     with self.assertRaises(SystemExit):culture.main()
    before=json.loads((root/'data/culture/current.json').read_text());self.assertEqual(len(before['items']),4)
    with patch.object(culture,'illustration') as artfn,patch.object(culture,'poetry',return_value=poem) as poemfn,patch.object(culture,'literature') as textfn,patch.object(culture,'music') as musicfn:
     culture.main();artfn.assert_not_called();textfn.assert_not_called();musicfn.assert_not_called();poemfn.assert_called_once()
     after=json.loads((root/'data/culture/current.json').read_text());self.assertEqual(len(after['items']),5)
     self.assertTrue(all(item in after['items'] for item in before['items']))
     poemfn.reset_mock();culture.main();poemfn.assert_not_called()
 def test_auto_ads_needs_no_manual_units_but_requires_consent_setup(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'config').mkdir();c=json.loads((ROOT/'config/site.json').read_text());c['site_url']='https://brief.example.test';c['adsense'].update(enabled=True,mode='auto',publisher_id='ca-pub-1234567890123456',cmp_enabled=True)
   p=root/'config/site.json';p.write_text(json.dumps(c))
   with patch.dict('os.environ',{},clear=True):self.assertTrue(load_config(root)['adsense']['enabled'])
   c['adsense']['cmp_enabled']=False;p.write_text(json.dumps(c))
   with patch.dict('os.environ',{},clear=True),self.assertRaises(ValueError):load_config(root)

if __name__=='__main__':unittest.main()
