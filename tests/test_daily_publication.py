import contextlib,copy,io,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,Mock
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from generate_research_summaries import merge_recent
from brief_contract import load_config

class DailyPublication(unittest.TestCase):
 def test_research_provider_failure_does_not_erase_recent_papers(self):
  old={r['key']:r for r in [{'key':'pnas','date':'2026-09-01'},{'key':'ssrn','date':'2026-08-30'},{'key':'older','date':'2026-07-01'}]}
  result=merge_recent(old,[{'key':'arxiv','date':'2026-09-06'}],'2026-09-06')
  self.assertEqual({x['key'] for x in result},{'pnas','ssrn','arxiv'})
 def test_changed_paper_metadata_replaces_outdated_summary(self):
  old={'one':{'key':'one','date':'2026-09-01','has_editorial':True,'headline':'Earlier claim'}}
  current={'key':'one','date':'2026-09-01','has_editorial':False,'headline':'Corrected paper title'}
  self.assertEqual(merge_recent(old,[current],'2026-09-06'),[current])
 def test_auto_ads_needs_no_manual_units_but_requires_consent_setup(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'config').mkdir();c=json.loads((ROOT/'config/site.json').read_text());c['site_url']='https://brief.example.test';c['adsense'].update(enabled=True,mode='auto',publisher_id='ca-pub-1234567890123456',cmp_enabled=True)
   p=root/'config/site.json';p.write_text(json.dumps(c))
   with patch.dict('os.environ',{},clear=True):self.assertTrue(load_config(root)['adsense']['enabled'])
   c['adsense']['cmp_enabled']=False;p.write_text(json.dumps(c))
   with patch.dict('os.environ',{},clear=True),self.assertRaises(ValueError):load_config(root)

if __name__=='__main__':unittest.main()
