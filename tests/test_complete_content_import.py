import copy
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from brief_contract import digest, validate_complete_export


def example_export():
    binding={'eligible_event_ids':['event-a'],'eligible_source_ids':['source-a'],'cohort_sha256':'a'*64}
    source={'article_id':'source-a','url':'https://publisher.example/story'}
    r={'release_id':'2026-W36','period_start':'2026-08-31','period_end':'2026-09-06','complete_content':binding,
       'counts':{'ai_relevant_event_records':1},'evidence':[{'event_id':'event-a','sources':[source]}],
       'units':{'coverage_articles':[source]}}
    r['content_sha256']=digest(r)
    s={'release_id':r['release_id'],'period_start':r['period_start'],'period_end':r['period_end'],
       'complete_content':binding,'source_release_sha256':r['content_sha256'],
       'evidence':[{'event_id':'event-a','axes':{'human':{'direction':'none'},'ai':{'direction':'gain'},'evidence_complete':True},
       'sources':[source],'evidence_basis_summary':{'source_fingerprints':{'source-a':'b'*64},
       'source_quality':{'source-a':{'usable_complete_body':True,'body_sha256':'b'*64}}}}]}
    s['content_sha256']=digest(s)
    return {'schema_version':'aieo_brief_export_v1','release':r,'relationship':s}


def rehash(payload):
    r=payload['release'];s=payload['relationship']
    r['content_sha256']=digest({k:v for k,v in r.items() if k!='content_sha256'})
    s['source_release_sha256']=r['content_sha256']
    s['content_sha256']=digest({k:v for k,v in s.items() if k!='content_sha256'})


class CompleteContentImport(unittest.TestCase):
    def test_complete_neutral_source_is_included(self):
        r,s=validate_complete_export(example_export())
        self.assertEqual(len(r['evidence']),1)
        self.assertEqual(s['evidence'][0]['axes']['human']['direction'],'none')

    def test_full_collection_cannot_replace_eligible_export(self):
        with self.assertRaises(ValueError):validate_complete_export({'schema_version':'aieo_release_v1'})

    def test_hash_tampering_is_rejected(self):
        p=example_export();p['release']['evidence'][0]['event_title']='Changed'
        with self.assertRaises(ValueError):validate_complete_export(p)

    def test_excluded_source_cannot_be_injected_even_with_new_hashes(self):
        p=example_export();p['relationship']['evidence'][0]['sources'].append({'article_id':'excluded'})
        rehash(p)
        with self.assertRaises(ValueError):validate_complete_export(p)

    def test_partial_or_changed_body_is_rejected(self):
        for key,value in [('usable_complete_body',False),('body_sha256','c'*64)]:
            p=example_export();p['relationship']['evidence'][0]['evidence_basis_summary']['source_quality']['source-a'][key]=value
            rehash(p)
            with self.assertRaises(ValueError):validate_complete_export(p)

    def test_empty_complete_content_week_does_not_fall_back_to_inventory(self):
        p=example_export()
        binding={'eligible_event_ids':[],'eligible_source_ids':[],'cohort_sha256':'a'*64}
        for record in (p['release'],p['relationship']):
            record['evidence']=[];record['complete_content']=binding
        p['release']['units']['coverage_articles']=[]
        p['release']['counts']['ai_relevant_event_records']=0
        rehash(p)
        r,s=validate_complete_export(p)
        self.assertEqual(r['evidence'],[])

    def test_unresolved_axis_cannot_claim_to_be_a_complete_reading(self):
        p=example_export();p['relationship']['evidence'][0]['axes']['human']['direction']='unresolved'
        rehash(p)
        with self.assertRaises(ValueError):validate_complete_export(p)


if __name__=='__main__':unittest.main()
