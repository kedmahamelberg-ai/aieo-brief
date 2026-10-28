import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from english_publication import EnglishPublication,digest,POLICY,NOTICE,content_version,non_latin,slots,culture_slots
from culture_library import validate_record

class EnglishPublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.row={'key':'culture:'+'a'*24,'kind':'culture','culture_type':'text','headline':'Papéis avulsos',
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
        self.assertEqual(out['sources'][0]['headline'],row['sources'][0]['headline'])
        self.assertTrue(out['brief_translation_note']);self.assertEqual(out['excerpt_parts'][0]['text'],out['excerpt'])
    def test_failure_has_english_notice_no_foreign_prose(self):
        eng=EnglishPublication(self.temp.name,False,self.checker);out=eng.apply(self.row)
        self.assertEqual(out['english_status'],'pending');self.assertEqual(out['sources'][0]['headline'],self.row['sources'][0]['headline'])
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

    def test_old_reviewed_literary_translation_is_reused(self):
        eng=EnglishPublication(self.temp.name,False,self.checker)
        old=[(p,v) for p,v in slots(self.row) if self.checker(v,str(p[-1]))]
        values={str(i):v for i,(_,v) in enumerate(old)}
        eng.cache[digest({'policy':POLICY,'fields':values})]=self.translator(values)
        eng.save()
        out=eng.apply(self.row)
        self.assertEqual(out['english_status'],'translated')
        self.assertEqual(out['excerpt'],'It was almost eleven when the reading ended.')
        self.assertEqual(out['sources'][0]['headline'],self.row['sources'][0]['headline'])

    def test_archived_culture_pending_translations_are_labelled(self):
        root=Path(__file__).resolve().parents[1]
        cache=self.temp.name+'/data/english/public-text.json'
        Path(cache).parent.mkdir(parents=True)
        Path(cache).write_bytes((root/'data/english/public-text.json').read_bytes())
        eng=EnglishPublication(self.temp.name,False)
        archive=json.loads((root/'data/archive/stories.json').read_text())['stories']
        culture=[item for item in archive if item.get('kind')=='culture']
        self.assertGreaterEqual(len(culture),200)
        public={item['key']:eng.apply(item) for item in culture}
        for original in culture:
            item=public[original['key']]
            if item['english_status']!='pending':
                continue
            with self.subTest(key=item['key']):
                self.assertEqual(item['brief_translation_note'],NOTICE)
                self.assertEqual(item['sources'][0]['url'],original['sources'][0]['url'])
                if item['culture_type'] in ('poetry','text','quote'):
                    self.assertEqual(item['excerpt'],NOTICE)
                if item['culture_type']=='poetry':
                    self.assertEqual(item['excerpt'],'\n'.join(item['poem_lines']))
                if item['culture_type']=='quote':
                    self.assertEqual(item['quote_context'],NOTICE)
                if item['culture_type']=='music':
                    self.assertEqual(item['headline'],'A cultural work awaiting English translation')
        gauguin=public['culture:21b374cc5db78518fc910f06']
        self.assertEqual(gauguin['headline'],'In the Waves (Dans les Vagues)')
        self.assertEqual(gauguin['rights']['label'],'CC0 image')

    def test_collection_marks_only_real_translation_work(self):
        root=Path(__file__).resolve().parents[1]
        counts={}
        for kind in ('art','poetry','text','quote','music'):
            rows=json.loads((root/f'data/culture/library-{kind}.json').read_text())
            self.assertEqual(len(rows),400)
            for row in rows:validate_record(row)
            counts[kind]=sum(bool(list(culture_slots(row))) for row in rows)
        self.assertEqual(counts,{'art':0,'poetry':22,'text':29,'quote':0,'music':4})

    def test_scots_poem_uses_notice_then_retries_translation(self):
        root=Path(__file__).resolve().parents[1]
        rows=json.loads((root/'data/culture/library-poetry.json').read_text())
        original=next(row for row in rows if row['key']=='culture:220e95c7ab0f123ae5ab4b3a')
        original={**original,'kind':'culture'}
        eng=EnglishPublication(self.temp.name,False)
        pending=eng.apply(original)
        self.assertEqual(pending['english_status'],'pending')
        self.assertNotIn('WHOM will you send',pending['excerpt'])
        self.assertEqual(pending['excerpt'],'\n'.join(pending['poem_lines']))
        self.assertEqual(original['language'],'Scots')
        retry=EnglishPublication(self.temp.name,True)
        def translated(values):
            output={k:'A reviewed English translation' for k in values}
            return {'policy':POLICY,'english':output,'review':{'english_only':True,'meaning_preserved':True,'attribution_preserved':True},'output_sha256':digest(output)}
        with patch.object(retry,'translate',side_effect=translated):
            self.assertEqual(retry.apply(original)['english_status'],'translated')
        self.assertEqual(EnglishPublication(self.temp.name,False).apply(original)['english_status'],'translated')

if __name__=='__main__':unittest.main()
