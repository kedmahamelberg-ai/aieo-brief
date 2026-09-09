import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from english_publication import EnglishPublication,digest,POLICY,content_version,non_latin,slots

class EnglishPublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.row={'key':'culture:'+'a'*24,'kind':'culture','headline':'Papéis avulsos',
                  'excerpt':'Eram quase onze horas quando acabou a leitura.',
                  'language':'Portuguese','creator':'Machado de Assis',
                  'poem_lines':[],'body_paragraphs':[],
                  'sources':[{'headline':'人工智能与教育','url':'https://example.test/a'}],
                  'rights':{'label':'Public domain','url':'https://example.test/license'},
                  'human_direction':'none','has_editorial':False}
        self.checker=lambda text,field: text in ['Papéis avulsos','Eram quase onze horas quando acabou a leitura.','人工智能与教育']
    def translator(self,values):
        mapping={'Papéis avulsos':'Miscellaneous Papers','Eram quase onze horas quando acabou a leitura.':'It was almost eleven when the reading ended.','人工智能与教育':'Artificial intelligence and education'}
        result={k:mapping[v] for k,v in values.items()}
        return {'policy':POLICY,'english':result,'review':{'english_only':True,'meaning_preserved':True,'attribution_preserved':True},'model':{'provider':'mock'},'output_sha256':digest(result)}
    def test_translation_preserves_original_and_identifiers(self):
        row=copy.deepcopy(self.row); eng=EnglishPublication(self.temp.name,True,self.checker)
        with patch.object(eng,'translate',side_effect=self.translator):out=eng.apply(row)
        self.assertEqual(row,self.row);self.assertEqual(out['headline'],'Miscellaneous Papers')
        self.assertEqual(out['key'],row['key']);self.assertEqual(out['sources'][0]['url'],row['sources'][0]['url'])
        self.assertEqual(out['creator'],'Machado de Assis');self.assertEqual(out['publication_language'],'en')
        self.assertEqual(out['sources'][0]['headline'],'Artificial intelligence and education')
        self.assertTrue(out['brief_translation_note']);self.assertEqual(out['excerpt_parts'][0]['text'],out['excerpt'])
    def test_failure_has_english_notice_no_foreign_prose(self):
        eng=EnglishPublication(self.temp.name,False,self.checker);out=eng.apply(self.row)
        self.assertEqual(out['english_status'],'pending');self.assertFalse(non_latin(out['sources'][0]['headline']))
        self.assertNotIn('Eram',out['excerpt']);self.assertEqual(eng.pending,1)
    def test_cache_avoids_repeated_model_calls(self):
        eng=EnglishPublication(self.temp.name,True,self.checker)
        with patch.object(eng,'translate',side_effect=self.translator) as call:eng.apply(self.row);self.assertEqual(call.call_count,1)
        nexteng=EnglishPublication(self.temp.name,False,self.checker)
        with patch.object(nexteng,'translate',side_effect=AssertionError('API must not run')):out=nexteng.apply(self.row)
        self.assertEqual(out['english_status'],'translated');self.assertEqual(nexteng.cached,1)
        content=nexteng.path.read_text();self.assertNotIn('Eram quase',content)
    def test_modified_source_invalidates_cache(self):
        eng=EnglishPublication(self.temp.name,True,self.checker)
        with patch.object(eng,'translate',side_effect=self.translator):eng.apply(self.row)
        self.row['excerpt']='Une nouvelle source.'
        eng.checker=lambda t,f:f in ('headline','excerpt')
        eng.allow_model=False
        self.assertEqual(eng.apply(self.row)['english_status'],'pending')
    def test_english_passthrough_and_content_version(self):
        eng=EnglishPublication(self.temp.name,checker=lambda t,f:False)
        out=eng.apply({'key':'event:'+'a'*36,'headline':'AI tools help researchers study images','kind':'news'})
        self.assertEqual(out['english_status'],'checked');first=content_version(out)[0]
        out['headline']='AI tools help researchers study sound';self.assertNotEqual(first,content_version(out)[0])
    def test_budget_stops_further_calls(self):
        eng=EnglishPublication(self.temp.name,True,self.checker)
        with patch.object(eng,'translate',side_effect=TimeoutError) as call:
            eng.apply(self.row);eng.apply(self.row);self.assertEqual(call.call_count,1)
    def test_nonlatin_detection(self):
        for text in ['人工智能','الذكاء الاصطناعي','исследование','研究']:self.assertTrue(non_latin(text))
        self.assertFalse(non_latin('Français, Portuguese and English'))

if __name__=='__main__':unittest.main()
