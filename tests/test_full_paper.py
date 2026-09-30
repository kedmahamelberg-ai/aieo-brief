import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from research_reading import extract_paper, needs_upgrade, READING_VERSION, allowed_pdf
import editorial_engine as engine

class FullPaperReading(unittest.TestCase):
    def test_direct_paper_reading_retains_the_last_page(self):
        text='A complete evidence sentence. '*3400+'Final-page limitation.'
        sources=[{'source_number':1,'evidence':text,'evidence_basis':'paper_text'}]
        with patch.object(engine.ai_runtime,'uses_openai',return_value=True):
            compiled,trace=engine.compile_evidence(sources)
        self.assertEqual(compiled,sources)
        self.assertIn('Final-page limitation.',compiled[0]['evidence'])
        self.assertFalse(trace)

    def test_every_page_is_read_and_identity_checked(self):
        pages=[Mock(),Mock(),Mock()]
        for i,p in enumerate(pages):p.extract_text.return_value=('Study title\n' if not i else '')+('Evidence about methods and results. '*60)+'\x00'
        reader=Mock(is_encrypted=False,pages=pages)
        with patch('pypdf.PdfReader',return_value=reader):
            result=extract_paper(b'%PDF-test','Study title')
            self.assertEqual(result['pages'],3)
            self.assertNotIn('\x00',result['text'])
            self.assertIn('[PDF page 3]',result['text'])
            with self.assertRaises(ValueError):extract_paper(b'%PDF-test','Other paper')
            pages[1].extract_text.return_value=''
            with self.assertRaises(ValueError):extract_paper(b'%PDF-test','Study title')
    def test_existing_abstracts_upgrade_and_unavailable_pdfs_retry(self):
        self.assertTrue(needs_upgrade({'has_editorial':True}))
        row={'has_editorial':True,'research_reading_version':READING_VERSION,'evidence_scope':'paper_text'}
        self.assertFalse(needs_upgrade(row))
        self.assertTrue(needs_upgrade({**row,'evidence_scope':'abstract','full_text_retry_after':'2020-01-01'}))
        self.assertFalse(needs_upgrade({**row,'evidence_scope':'abstract','full_text_retry_after':'2099-01-01'}))
        self.assertFalse(allowed_pdf('https://arxiv.org.evil.example/paper'))
    def test_segment_ids_resolve_to_exact_evidence(self):
        with patch.object(engine,'call_json',return_value={'note':'A supported note.','quote_ids':[0]}):
            note,quotes=engine.read_segment('The complete source sentence describes a tested method.',None)
        self.assertEqual(quotes,['The complete source sentence describes a tested method.'])

    def test_segment_quote_catalog_uses_verified_quotes_not_note_text(self):
        source={'source_number':1,'evidence':'A paraphrased note.', 'evidence_quotes':['An exact passage from the paper.']}
        self.assertEqual(engine.research_quotes([source]), source['evidence_quotes'])
        self.assertEqual(engine.draft_schema([source],'paper')['properties']['claim_status']['enum'],['study'])
