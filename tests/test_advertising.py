import copy,json,os,sys,tempfile,unittest,subprocess
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from build_site import advertising_eligible,sponsor_is_active
from brief_contract import load_config
from check_observatory_update import brief_url
class Advertising(unittest.TestCase):
 def test_ads_need_actual_editorial_content(self):
  story={'kind':'news','has_editorial':True,'what_happened':'A supported finding'}
  self.assertTrue(advertising_eligible('story',story));self.assertTrue(advertising_eligible('home',news=[story]*4))
  for page in ['account','privacy','notifications','saved','culture','research']:self.assertFalse(advertising_eligible(page,story,[story]*4))
  self.assertFalse(advertising_eligible('story',{**story,'kind':'culture'}));self.assertFalse(advertising_eligible('story',{**story,'has_editorial':False}))
 def test_ad_slot_typos_fail_before_publication(self):
  with tempfile.TemporaryDirectory() as temp,patch.dict(os.environ,{},clear=True):
   root=Path(temp);(root/'config').mkdir();c=json.loads((ROOT/'config/site.json').read_text());c['adsense']['slots']['rail']='wrong';(root/'config/site.json').write_text(json.dumps(c))
   with self.assertRaises(ValueError):load_config(root)
 def test_custom_domain_used_by_handoff_and_variable_override_preserved(self):
  with patch.dict(os.environ,{},clear=True):self.assertEqual(brief_url(),'https://brief.hamelberg-ai.com')
  with patch.dict(os.environ,{'BRIEF_SITE_URL':'https://other.example/'}):self.assertEqual(brief_url(),'https://other.example')
 def test_settings_update_is_atomic_and_preserves_other_features(self):
  with tempfile.TemporaryDirectory() as temp:
   parent=Path(temp);repo=parent/'brief';(repo/'config').mkdir(parents=True);target=repo/'config/site.json';original=json.loads((ROOT/'config/site.json').read_text());original['future_feature']={'enabled':True};target.write_text(json.dumps(original));setting=parent/'Brief-Monetization.json'
   def run(value):
    setting.write_text(json.dumps(value));return subprocess.run(['perl',str(ROOT/'owner-tools/apply-monetization.pl'),str(target),str(setting)],capture_output=True,text=True)
   p={'schema_version':'aieo_brief_monetization_v1','support_url':'https://ko-fi.com/reader'}
   self.assertEqual(run(p).returncode,0);updated=json.loads(target.read_text());self.assertEqual({k:v for k,v in updated.items() if k!='support_url'},{k:v for k,v in original.items() if k!='support_url'})
   self.assertIn('already up to date',run(p).stdout);before=target.read_bytes();self.assertNotEqual(run({**p,'support_url':'javascript:bad'}).returncode,0);self.assertEqual(target.read_bytes(),before)
   ad={**original['adsense'],'enabled':True,'cmp_enabled':True,'mode':'placements','slots':{'feed':'12345'}}
   self.assertEqual(run({'schema_version':p['schema_version'],'adsense':ad}).returncode,0);self.assertTrue(json.loads(target.read_text())['adsense']['enabled']);self.assertTrue(list(parent.glob('Brief-settings-backup-*')));self.assertFalse(list(repo.glob('Brief-settings-backup-*')))

 def test_direct_sponsorship_obeys_campaign_dates_and_preview(self):
  config={'sponsor':{'enabled':True,'starts':'2026-09-08','ends':'2026-09-15'}}
  self.assertTrue(sponsor_is_active(config,'2026-09-08'))
  self.assertTrue(sponsor_is_active(config,'2026-09-15'))
  for day in ('2026-09-07','2026-09-16'):self.assertFalse(sponsor_is_active(config,day))
  self.assertFalse(sponsor_is_active(config,'2026-09-10',True))
  config['sponsor']['enabled']=False;self.assertFalse(sponsor_is_active(config,'2026-09-10'))
