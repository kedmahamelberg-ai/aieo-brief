import copy,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from brief_contract import validate_pair,load_config,digest,PROMPT_VERSION
from build_site import cards,version_valid
from generate_editorial_stories import source_payload,candidates
from source_evidence_quality import evidence_chunks
from editorial_engine import validate_draft,compile_evidence,review_scope
class Publication(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.release=json.loads((ROOT/'data/preview/release.json').read_text());cls.sym=json.loads((ROOT/'data/preview/symbiosis.json').read_text());cls.seed=json.loads((ROOT/'data/preview/editorial.json').read_text())
 def test_110_independent_records(self):
  c=validate_pair(self.release,self.sym);self.assertEqual(sum(c['human'].values()),110);self.assertEqual(c['human'],{'gain':45,'loss':3,'mixed':26,'none':8,'unresolved':28});self.assertEqual(c['ai']['mixed'],38)
 def test_old_or_partial_classification_cannot_publish(self):
  for change in ('hash','missing','duplicate','axis'):
   sym=copy.deepcopy(self.sym)
   if change=='hash':sym['source_release_sha256']='old'
   elif change=='missing':sym['evidence'].pop()
   elif change=='duplicate':sym['evidence'][0]=sym['evidence'][1]
   else:sym['evidence'][0]['axes']['human']['direction']='enabling'
   with self.assertRaises(ValueError):validate_pair(self.release,sym)
 def test_stale_rewrite_falls_back_without_inventing_copy(self):
  seed=copy.deepcopy(self.seed);first=next(iter(seed));seed[first]['evidence_basis_summary']['axes_sha256']='old'
  records=cards(self.release,self.sym,{}, {},seed,True);row=next(x for x in records if x['event_id']==first)
  self.assertFalse(row['has_editorial']);self.assertEqual(row['headline'],row['original_headline'])
 def test_every_source_and_discovery_market_survives(self):
  records=cards(self.release,self.sym,{}, {},self.seed,True)
  self.assertEqual(sum(x['source_count'] for x in records),111)
  self.assertEqual(set(c for x in records for c in x['markets']),{'CA','CN','FR','GB','US'})
  self.assertTrue(all('evidence_text' not in json.dumps(x) for x in records))
 def test_server_keys_are_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'config').mkdir();c=json.loads((ROOT/'config/site.json').read_text());c['supabase_publishable_key']='sb_secret_do_not_publish';(p/'config/site.json').write_text(json.dumps(c))
   with patch.dict('os.environ',{},clear=True),self.assertRaises(ValueError):load_config(p)
 def test_body_gate_uses_bytes_not_a_full_body_label(self):
  full={'evidence_basis':'full_source','evidence_text':'A source reporting a detailed account of the use of artificial intelligence in a workplace. '*8}
  partial={**full,'evidence_text':full['evidence_text']+' You have 67.94% of this article'}
  self.assertEqual(len(source_payload([full,partial])),1)
  self.assertEqual(source_payload([full])[0]['evidence'],full['evidence_text'].strip())
 def test_chunk_boundaries_cover_the_final_paragraph(self):
  text=('paragraph line\n'*2500)+'A crucial correction at the end.';chunks=evidence_chunks(text,limit=3600,overlap=160)
  covered=set()
  for c in chunks:covered.update(range(c['start'],c['end']))
  self.assertEqual(len(covered),len(text));self.assertTrue(chunks[-1]['text'].endswith('A crucial correction at the end.'))
 def test_compiled_quotes_remain_available_to_the_writer(self):
  source='A measured benefit was reported for the tested group. '*140
  with patch('editorial_engine.call_json',return_value={'note':'The tested group showed a benefit.','quotes':['A measured benefit was reported']}):
   compiled,trace=compile_evidence([{'source_number':1,'evidence':source}])
  self.assertTrue(trace);self.assertTrue(all(x['evidence_quotes'] for x in compiled));self.assertEqual(trace[-1]['end'],len(source))
 def draft(self):
  source='Researchers surveyed 142 musicians about AI. A large majority raised concerns about payment. The survey cannot represent every musician.'
  d={'editorial_headline':'Musician survey highlights concern about AI and income','editorial_deck':'Respondents describe worries about how their work is valued.','what_happened':'A survey asked 142 music professionals about AI.','why_it_matters':'The responses raise questions about fair payment.','for_humans':'Participants describe concerns.','for_ai':'The study asks about its use.','body_paragraphs':['The findings describe what respondents said, with limits on wider conclusions.'],'claim_status':'study','limitation':'A survey is not a population census.','support':[{'field':f,'source_number':1,'quote':'A large majority raised concerns about payment.'} for f in ('editorial_headline','what_happened','why_it_matters')]}
  return d,[{'source_number':1,'headline':'Musician study','evidence':source}]
 def test_unsupported_numbers_and_missing_support_are_rejected(self):
  d,s=self.draft();validate_draft(d,s)
  d['what_happened']='A survey asked 263 music professionals about AI.'
  with self.assertRaises(ValueError):validate_draft(d,s)
  d,s=self.draft();d['support'][0]['quote']='An invented sentence that is absent.'
  with self.assertRaises(ValueError):validate_draft(d,s)
 def test_scope_review_rejects_a_changed_percentage_population(self):
  d,s=self.draft()
  with patch('editorial_engine.call_json',return_value={'headline_supported':True,'population_preserved':False,'claim_status_preserved':True,'no_unstated_effects':True,'main_story_only':True,'reason':'The headline generalises a subgroup to all respondents.'}),self.assertRaises(ValueError):review_scope(d,s)
 def test_preprints_need_a_limit_and_study_status(self):
  d,s=self.draft();d['limitation']=''
  with self.assertRaises(ValueError):validate_draft(d,s,'preprint')
 def test_new_independent_axes_do_not_need_legacy_reviewed_flag(self):
  r=copy.deepcopy(self.release);eid=next(x['event_id'] for x in self.sym['evidence'] if x['axes']['evidence_complete']);r['evidence']=[next(x for x in r['evidence'] if x['event_id']==eid)];sym={'evidence':[next(x for x in self.sym['evidence'] if x['event_id']==eid)]}
  evidence={eid:[{'evidence_basis':'full_source','evidence_text':'This article contains specific information about an artificial intelligence deployment. '*8}]}
  with patch('generate_editorial_stories.ROOT',Path(tempfile.gettempdir())/'no-brief-retry-state'):
   selected,counts,_=candidates(r,sym,({}, {},evidence,{}))
  self.assertEqual(len(selected),1);self.assertEqual(counts['needs_model'],1)
if __name__=='__main__':unittest.main()
