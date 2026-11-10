import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from research_reading import extract_paper, extract_arxiv_html, read_paper, read_pmc_xml, needs_upgrade, READING_VERSION, PDF_READER_VERSION, allowed_pdf, publisher_pdf_urls, style_problem
import editorial_engine as engine
from validate_public_site import validate_research_reading, validate_weekly_research_window

class FullPaperReading(unittest.TestCase):
    def test_practitioner_style_rejects_unexplained_shorthand_and_vague_titles(self):
        self.assertTrue(style_problem({'headline':'Native RL boosts repair rates','what_happened':'SFT was compared with RL.'}))
        self.assertTrue(style_problem({'headline':'Unified models improve readiness'}))
        self.assertFalse(style_problem({'headline':'Training helps an AI image maker repair its mistakes',
                                      'what_happened':'The model learned through rewards for successful repairs.'}))
        self.assertTrue(needs_upgrade({'has_editorial':True,'research_reading_version':READING_VERSION,
                                       'evidence_scope':'paper_text','headline':'Native RL boosts repair rates'}))

    def test_publication_accepts_verified_paper_reading_but_rejects_false_labels(self):
        paper={'evidence_scope':'paper_text','limitation':'Lab results only.',
               'full_text_status':'read','paper_pages':36,'paper_text_sha256':'a'*64,
               'summary_basis':'Summary of the paper'}
        validate_research_reading(paper)
        for changed in ({'paper_text_sha256':''},{'full_text_status':'pdf_unavailable'},
                        {'evidence_scope':'abstract'},{'limitation':''}):
            with self.assertRaises(ValueError):validate_research_reading({**paper,**changed})

    def test_weekly_research_window_uses_canonical_paper_dates(self):
        overview={'period_start':'2026-10-05','period_end':'2026-10-11',
                  'research':{'source_hashes':{'paper:one':'hash','paper:two':'hash'},
                              'papers':[{'key':'paper:one'},{'key':'paper:two'}]}}
        canonical=[{'key':'paper:one','date':'2026-10-07'},
                   {'key':'paper:two','date':'2026-10-11'}]
        validate_weekly_research_window(overview,canonical)
        with self.assertRaises(ValueError):
            validate_weekly_research_window(overview,[canonical[0],{'key':'paper:two','date':'2026-10-12'}])

    def test_long_paper_reading_retains_the_last_page(self):
        text='A complete evidence sentence. '*6500+'Final-page limitation.'
        sources=[{'source_number':1,'evidence':text,'evidence_basis':'paper_text'}]
        def note(segment,deadline):
            return segment[-250:], ['A complete evidence sentence.']
        with patch.object(engine.ai_runtime,'uses_openai',return_value=True), patch.object(engine,'read_segment',side_effect=note):
            compiled,trace=engine.compile_evidence(sources)
        self.assertTrue(trace)
        self.assertEqual(trace[0]['start'],0)
        self.assertEqual(trace[-1]['end'],len(text))
        self.assertIn('Final-page limitation.',compiled[-1]['evidence'])

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
        self.assertTrue(needs_upgrade({**row,'evidence_scope':'abstract','full_text_status':'pdf_text_unreadable',
                                       'pdf_reader_version':1,'full_text_retry_after':'2099-01-01'}))
        self.assertFalse(needs_upgrade({**row,'evidence_scope':'abstract','full_text_status':'pdf_text_unreadable',
                                        'pdf_reader_version':PDF_READER_VERSION,'full_text_retry_after':'2099-01-01'}))
        self.assertFalse(allowed_pdf('https://arxiv.org.evil.example/paper'))

    def test_unreadable_arxiv_pdf_uses_complete_verified_html(self):
        title='When Should We Intervene at Test Time?'
        html=('<html><body><nav>Site navigation</nav><article class="ltx_document">'
              '<h1 class="ltx_title_document">'+title+'</h1>'
              '<div class="ltx_abstract">The abstract describes the problem. </div>'
              '<section><h2>Methods</h2><p>'+('Methods explain the intervention and its evidence. '*35)+'</p></section>'
              '<section><h2>Results</h2><p>'+('Results include observed tradeoffs and limits. '*35)+'</p></section>'
              '</article><footer>Report an issue</footer></body></html>').encode()
        def response(content, content_type):
            item=MagicMock(status_code=200,headers={'Content-Type':content_type},is_redirect=False)
            item.__enter__.return_value=item
            item.iter_content.return_value=[content]
            return item
        paper={'arxiv_id':'2610.37658v1','pdf_url':'https://arxiv.org/pdf/2610.37658v1',
               'original_headline':title}
        with patch('research_reading.requests.get',side_effect=[response(b'not a pdf','application/pdf'),response(html,'text/html')]) as get:
            reading=read_paper(paper)
        self.assertEqual(reading['status'],'read')
        self.assertEqual(reading['format'],'arxiv_html')
        self.assertEqual(reading['sections'],2)
        self.assertIn('Results include observed tradeoffs',reading['text'])
        self.assertNotIn('Site navigation',reading['text'])
        self.assertEqual(get.call_args_list[1].args[0],'https://arxiv.org/html/2610.37658v1')
        validate_research_reading({'evidence_scope':'paper_text','summary_basis':'Summary of the paper',
                                   'full_text_status':'read','limitation':'Only two controlled tests were reported.',
                                   'arxiv_id':paper['arxiv_id'],'paper_source_url':reading['url'],
                                   'paper_sections':reading['sections'],'paper_text_sha256':reading['text_sha256']})
        with self.assertRaises(ValueError):
            validate_research_reading({'evidence_scope':'paper_text','summary_basis':'Summary of the paper',
                                       'full_text_status':'read','limitation':'Only two controlled tests were reported.',
                                       'arxiv_id':paper['arxiv_id'],'paper_source_url':'https://arxiv.org/html/9999.99999',
                                       'paper_sections':reading['sections'],'paper_text_sha256':reading['text_sha256']})
        with self.assertRaisesRegex(ValueError,'paper_identity_mismatch'):
            extract_arxiv_html(html,'Another Paper')
        with self.assertRaisesRegex(ValueError,'incomplete_html_article'):
            extract_arxiv_html(html.replace(b'</article>',b''),title)

    def test_pnas_pmc_full_text_fallback_requires_matching_doi_and_title(self):
        title = 'Quantifying ancient architecture: Stone-level machine learning reveals architectural variation and settlement growth at Shivta'
        doi = '10.1073/pnas.2628851123'
        xml = ('<article><front><article-meta><article-id pub-id-type="doi">' + doi +
               '</article-id><title-group><article-title>' + title +
               '</article-title></title-group><abstract><p>Article abstract.</p></abstract>'
               '</article-meta></front><body><sec><title>Methods</title><p>' +
               'The study measured individual building stones. ' * 45 +
               '</p></sec><sec><title>Results</title><p>' +
               'The authors compared masonry across structures and describe limitations. ' * 45 +
               '</p></sec></body></article>').encode()
        search = Mock()
        search.json.return_value = {'resultList': {'result': [{'doi': doi, 'pmcid': 'PMC13732063', 'isOpenAccess': 'Y'}]}}
        search.raise_for_status.return_value = None
        article = MagicMock()
        article.__enter__.return_value = article
        article.iter_content.return_value = [xml]
        paper = {'source': 'pnas', 'doi': doi, 'original_headline': title, 'pdf_url': ''}
        with patch('research_reading.requests.get', side_effect=[search, article]) as get:
            reading = read_paper(paper)
        self.assertEqual(reading['status'], 'read')
        self.assertEqual(reading['format'], 'pmc_xml')
        self.assertIn('The study measured individual building stones', reading['text'])
        self.assertEqual(get.call_args_list[1].args[0],
                         'https://www.ebi.ac.uk/europepmc/webservices/rest/PMC13732063/fullTextXML')
        validate_research_reading({'evidence_scope': 'paper_text', 'summary_basis': 'Summary of the paper',
                                   'full_text_status': 'read', 'limitation': 'Site-specific study.',
                                   'doi': doi, 'paper_doi': doi, 'paper_pmcid': reading['pmcid'],
                                   'paper_source_url': reading['url'], 'paper_sections': reading['sections'],
                                   'paper_text_sha256': reading['text_sha256']})
        bad_xml = xml.replace(doi.encode(), b'10.1073/pnas.9999999999')
        article.iter_content.return_value = [bad_xml]
        with patch('research_reading.requests.get', side_effect=[search, article]):
            self.assertEqual(read_pmc_xml(paper)['status'], 'paper_identity_mismatch')

    def test_arxiv_title_image_missing_one_letter_still_matches(self):
        title = 'ScholarCatalyst: A Benchmark for Retrieving Papers That Inspire New Research'
        html = ('<article class="ltx_document"><h1 class="ltx_title_document">Scholar'
                '<img src="logo.png" alt="[Uncaptioned image]">atalyst: A Benchmark for<br>'
                'Retrieving Papers that Inspire New Research'
                '</h1><div class="ltx_abstract">Abstract.</div><section><p>' +
                'The paper describes its methodology and limitations. ' * 35 +
                '</p></section><section><p>' +
                'The results include comparisons with competing approaches. ' * 35 +
                '</p></section></article>').encode()
        self.assertEqual(extract_arxiv_html(html, title)['sections'], 2)
        with self.assertRaisesRegex(ValueError, 'paper_identity_mismatch'):
            extract_arxiv_html(html, title.replace('Benchmark', 'Framework'))

    def test_prior_arxiv_pdf_failure_gets_one_immediate_html_retry(self):
        row={'has_editorial':True,'research_reading_version':READING_VERSION,'evidence_scope':'abstract',
             'arxiv_id':'2610.37658v1','full_text_status':'pdf_text_unreadable',
             'pdf_reader_version':PDF_READER_VERSION,'full_text_retry_after':'2099-01-01'}
        self.assertTrue(needs_upgrade(row))
        self.assertFalse(needs_upgrade({**row,'html_reader_version':1}))

    def test_long_complete_pdf_is_read_without_truncating_its_last_page(self):
        pages=[Mock() for _ in range(169)]
        for i,page in enumerate(pages):
            page.extract_text.return_value=('Study title\n' if i == 0 else '')+('Methods, findings, and limitations. '*80)
        reader=Mock(is_encrypted=False,pages=pages)
        with patch('pypdf.PdfReader',return_value=reader):
            result=extract_paper(b'%PDF-test','Study title')
        self.assertEqual(result['pages'],169)
        self.assertGreater(len(result['text']),210000)
        self.assertIn('[PDF page 169]',result['text'])

    def test_one_sparse_figure_page_does_not_hide_an_otherwise_readable_paper(self):
        pages=[Mock() for _ in range(15)]
        for i,page in enumerate(pages):
            page.extract_text.return_value=('Study title\n' if i == 0 else '')+('Study evidence and limitations. '*40)
        pages[8].extract_text.return_value='Figure 4'
        with patch('pypdf.PdfReader',return_value=Mock(is_encrypted=False,pages=pages)):
            self.assertEqual(extract_paper(b'%PDF-test','Study title')['pages'],15)
            pages[9].extract_text.return_value='Figure 5'
            with self.assertRaisesRegex(ValueError,'incomplete_text_extraction'):
                extract_paper(b'%PDF-test','Study title')

    def test_pdf_identity_allows_latex_math_and_added_year_but_no_changed_claim(self):
        pages=[Mock(),Mock()]
        pages[1].extract_text.return_value='Methods and limitations. '*100
        with patch('pypdf.PdfReader',return_value=Mock(is_encrypted=False,pages=pages)):
            pages[0].extract_text.return_value='A Quasipolynomial Algorithm for ℓ∞ Contractions\n'+'Abstract and methods. '*80
            self.assertEqual(extract_paper(b'%PDF-test',r'A Quasipolynomial Algorithm for $\ell_\infty$ Contractions')['pages'],2)
            pages[0].extract_text.return_value='From Reactive Containment to Proactive Assurance: Lessons from the 2026 OpenAI, Anthropic, and Google Agent Security Incidents\n'+'Abstract and methods. '*80
            self.assertEqual(extract_paper(b'%PDF-test','From Reactive Containment to Proactive Assurance: Lessons from OpenAI, Anthropic, and Google Agent Security Incidents')['pages'],2)
            with self.assertRaisesRegex(ValueError,'paper_identity_mismatch'):
                extract_paper(b'%PDF-test','From Reactive Containment to Proactive Assurance: Lessons from Microsoft, Anthropic, and Google Agent Security Incidents')

    def test_crossref_unspecified_pnas_pdf_is_accepted_only_for_exact_doi(self):
        doi='10.1073/pnas.2628851123'
        good='https://pnas.org/doi/pdf/'+doi
        links=[{'URL':good,'content-type':'unspecified'},
               {'URL':'https://pnas.org/doi/pdf/10.1073/pnas.999','content-type':'unspecified'},
               {'URL':good+'.evil.example','content-type':'unspecified'}]
        self.assertEqual(publisher_pdf_urls(doi,links),[good])
    def test_segment_ids_resolve_to_exact_evidence(self):
        with patch.object(engine,'call_json',return_value={'note':'A supported note.','quote_ids':[0]}):
            note,quotes=engine.read_segment('The complete source sentence describes a tested method.',None)
        self.assertEqual(quotes,['The complete source sentence describes a tested method.'])

    def test_segment_quote_catalog_uses_verified_quotes_not_note_text(self):
        source={'source_number':1,'evidence':'A paraphrased note.', 'evidence_quotes':['An exact passage from the paper.']}
        self.assertEqual(engine.research_quotes([source]), source['evidence_quotes'])
        self.assertEqual(engine.draft_schema([source],'paper')['properties']['claim_status']['enum'],['study'])
