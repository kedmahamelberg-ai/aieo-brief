from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

from weekly_overviews import prepare_weekly_overviews, social_queue
from research_affiliations import clean_institutions, enrich_affiliations
from search_metadata import weekly_overview_with_canonical_links
import build_site


class WeeklyOverviewTests(unittest.TestCase):
    def test_saved_overview_links_follow_current_article_urls(self):
        saved = {
            'markets': {'entries': [{'story': {'path': 'story/old/index.html'}}]},
            'research': {'papers': [{'path': 'research/old/index.html'}]},
        }
        items = [
            {'path': 'story/current/index.html', 'legacy_paths': ['story/old/index.html']},
            {'path': 'research/current/index.html', 'legacy_paths': ['research/old/index.html']},
        ]
        rendered = weekly_overview_with_canonical_links(saved, items)
        self.assertEqual(rendered['markets']['entries'][0]['story']['path'], 'story/current/index.html')
        self.assertEqual(rendered['research']['papers'][0]['path'], 'research/current/index.html')
        self.assertEqual(saved['markets']['entries'][0]['story']['path'], 'story/old/index.html')

    def news(self):
        rows=[]
        for index,(code,name) in enumerate((('CA','Canada'),('CN','China'),('FR','France'),('GB','United Kingdom'),('US','United States'))):
            rows.append({'key':f'event:{index}','headline':f'{name} tests a new AI policy and public service approach','deck':'A source-backed explanation of what changed and what remains uncertain.','path':f'story/{index}/index.html','publisher':'Example source','sources':[{'url':f'https://example.com/{index}','publisher':'Example source'}],'markets':[code],'topic':'policy','has_editorial':True,'daily_rank':index})
        return rows

    def research(self):
        return [{'key':'paper:123','headline':'A reliable agent benchmark','original_headline':'A reliable agent benchmark','deck':'The benchmark tests whether agents remain faithful under changed instructions.','url':'https://arxiv.org/abs/1234.5678','path':'research/paper-123/index.html','authors':['A. Researcher'],'institutions':['Example University'],'publisher':'arXiv','research_label':'Preprint','date':'2026-09-05','has_editorial':True,'source_verified_at':'2026-09-05T10:00:00Z','affiliation_source_url':'https://openalex.org/W1'}]

    def test_sub_minute_and_market_scope(self):
        with tempfile.TemporaryDirectory() as folder:
            current,history=prepare_weekly_overviews(self.news(),self.research(),{'release_id':'2026-W36','period_start':'2026-08-31','period_end':'2026-09-06'},Path(folder),write_archive=True)
            self.assertEqual(len(current['markets']['entries']),5)
            self.assertLessEqual(current['markets']['word_count'],145)
            self.assertIn('not a forecast',current['markets']['scope_note'])
            self.assertEqual(history[0]['release_id'],'2026-W36')
            saved=json.loads((Path(folder)/'data/weekly-overviews/history.json').read_text())
            self.assertEqual(saved['overviews'][0]['content_sha256'],current['content_sha256'])

    def test_research_keeps_institution_and_source(self):
        with tempfile.TemporaryDirectory() as folder:
            current,_=prepare_weekly_overviews(self.news(),self.research(),{'release_id':'2026-W36','period_start':'2026-08-31','period_end':'2026-09-06'},Path(folder))
            paper=current['research']['papers'][0]
            self.assertEqual(paper['institutions'],['Example University'])
            self.assertTrue(paper['url'].startswith('https://'))
            self.assertLessEqual(current['research']['word_count'],145)

    def test_output_is_deterministic_and_social_links_are_exact(self):
        with tempfile.TemporaryDirectory() as folder:
            release={'release_id':'2026-W36','period_start':'2026-08-31','period_end':'2026-09-06'}
            first,_=prepare_weekly_overviews(self.news(),self.research(),release,Path(folder))
            second,_=prepare_weekly_overviews(self.news(),self.research(),release,Path(folder))
            self.assertEqual(first['content_sha256'],second['content_sha256'])
            queue=social_queue(first,'https://brief.example')
            self.assertEqual(len(queue['items']),2)
            self.assertTrue(queue['items'][0]['destination'].startswith('https://brief.example/week-from-above/'))

    def test_past_research_review_stays_published_after_source_refresh(self):
        root = Path(__file__).resolve().parents[1]
        archived = next(x for x in json.loads((root/'data/weekly-overviews/history.json').read_text())['overviews']
                        if x['release_id'] == '2026-W43')
        approval = json.loads((root/'data/weekly-overviews/approved/2026-W43.json').read_text())
        approved_research = approval['research']
        papers = [dict(paper) for paper in approved_research['papers']]
        release = {'release_id': '2026-W44', 'period_start': '2026-10-26', 'period_end': '2026-11-01'}
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder)/'data/weekly-overviews/history.json'
            destination.parent.mkdir(parents=True)
            destination.write_text(json.dumps({'schema_version': 'aieo_weekly_overview_archive_v1',
                                               'overviews': [{**archived, 'research': approved_research}]}))
            papers[0]['has_editorial'] = False
            _, preserved = prepare_weekly_overviews([], [], release, Path(folder), source_research=papers)
            old = next(x for x in preserved if x['release_id'] == '2026-W43')
            self.assertEqual(old['research'], approved_research)
            self.assertEqual(old['markets'], archived['markets'])
            pending_archive = json.loads(json.dumps({**archived, 'research': approved_research}))
            pending_archive['research'].update(status='pending', prose=[], papers=[],
                                               pending_reason='approved_sources_changed')
            destination.write_text(json.dumps({'schema_version': 'aieo_weekly_overview_archive_v1',
                                               'overviews': [pending_archive]}))
            approval_path = Path(folder)/'data/weekly-overviews/approved/2026-W43.json'
            approval_path.parent.mkdir(parents=True)
            approval_path.write_text(json.dumps(approval))
            _, restored = prepare_weekly_overviews([], [], release, Path(folder), source_research=papers)
            old = next(x for x in restored if x['release_id'] == '2026-W43')
            self.assertEqual(old['research'], approved_research)
            self.assertEqual(old['editorial_status'], 'ready')


class ResearchAffiliationTests(unittest.TestCase):
    def paper(self):
        return {
            'key':'paper:test',
            'original_headline':'Verified AI paper',
            'url':'https://example.org/paper',
            'date':'2026-09-05',
            'authors':['A. Researcher'],
        }

    def test_source_and_institution_are_recorded_only_after_checks(self):
        paper=self.paper()
        work={'id':'https://openalex.org/W123','authorships':[{'institutions':[{'display_name':'Example University'}]}]}
        with patch('research_affiliations._verify_source',return_value=True), patch('research_affiliations._lookup',return_value=work), patch('research_affiliations.time.sleep'):
            result=enrich_affiliations([paper])
        self.assertTrue(paper.get('source_verified_at'))
        self.assertEqual(paper['institutions'],['Example University'])
        self.assertEqual(paper['affiliation_source_url'],'https://openalex.org/W123')
        self.assertTrue(result[0]['source_verified'])

    def test_failed_checks_do_not_invent_verification_or_affiliation(self):
        paper=self.paper()
        with patch('research_affiliations._verify_source',return_value=False), patch('research_affiliations._lookup',return_value=None), patch('research_affiliations.time.sleep'):
            result=enrich_affiliations([paper])
        self.assertNotIn('source_verified_at',paper)
        self.assertEqual(paper['institutions'],[])
        self.assertFalse(result[0]['source_verified'])

    def test_arxiv_author_affiliations_do_not_use_repository_host(self):
        paper={**self.paper(),'arxiv_id':'2610.31662v1','authors':['Isaac Gibbs','Elise L. Han'],
               'institutions':[],'affiliation_checked_at':'2026-10-23T17:04:52Z'}
        html='''<div class="ltx_authors"><span class="ltx_td">Isaac Gibbs</span>
        <span class="ltx_td">University of Toronto</span><span class="ltx_td">Elise L. Han</span>
        <span class="ltx_td">Stanford University</span></div>'''
        work={'id':'https://openalex.org/W7223293283','authorships':[],
              'primary_location':{'source':{'display_name':'arXiv (Cornell University)'}}}
        with patch('research_affiliations._verify_source',return_value=True), patch('research_affiliations._lookup',return_value=work), patch('research_affiliations.requests.get',return_value=type('Response',(),{'text':html,'raise_for_status':lambda self:None})()), patch('research_affiliations.time.sleep'):
            result=enrich_affiliations([paper])
        self.assertEqual(paper['institutions'],['University of Toronto','Stanford University'])
        self.assertEqual(paper['affiliation_source_url'],'https://arxiv.org/html/2610.31662v1')
        self.assertEqual(result[0]['status'],'arxiv_authors')
        self.assertTrue(paper['affiliation_fallback_checked_at'])

    def test_arxiv_nested_author_cells_keep_universities_separate(self):
        paper={**self.paper(),'arxiv_id':'2610.37658v1','authors':['Jiahao Zhang']}
        html='''<div class="ltx_authors"><span class="ltx_td"><span class="ltx_p">
        <span class="ltx_text">Jiahao Zhang</span>Zhengzhou University of Aeronautics
        </span><span class="ltx_p">author@example.org</span></span></div>'''
        with patch('research_affiliations._verify_source',return_value=True), patch('research_affiliations._lookup',return_value=None), patch('research_affiliations.requests.get',return_value=type('Response',(),{'text':html,'raise_for_status':lambda self:None})()), patch('research_affiliations.time.sleep'):
            enrich_affiliations([paper])
        self.assertEqual(paper['institutions'],['Zhengzhou University of Aeronautics'])

    def test_arxiv_explicit_affiliations_include_acronyms_and_labs(self):
        paper={**self.paper(),'arxiv_id':'2610.37666v1','authors':['Chaehyun Kim']}
        html='''<div class="ltx_authors"><span class="ltx_personname">Chaehyun Kim</span>
        <span class="ltx_contact ltx_role_affiliation"><span class="ltx_contact_name">Affiliation: </span><span class="ltx_text">NVIDIA</span></span>
        <span class="ltx_contact ltx_role_affiliation"><span class="ltx_contact_name">Affiliation: </span><span class="ltx_text">KAIST</span></span></div>'''
        with patch('research_affiliations._verify_source',return_value=True), patch('research_affiliations._lookup',return_value=None), patch('research_affiliations.requests.get',return_value=type('Response',(),{'text':html,'raise_for_status':lambda self:None})()), patch('research_affiliations.time.sleep'):
            enrich_affiliations([paper])
        self.assertEqual(paper['institutions'],['NVIDIA','KAIST'])

    def test_author_block_debris_is_not_an_institution(self):
        values=['Nicolas Ballas2','1Courant Institute, New York University',
                'Courant Institute, New York University',
                '1National University of Singapore2University of Oxford',
                'National University of Singapore','University of Oxford',
                'Project Page:https://flide.org','Source Code:https://github.com/example',
                'Cambridge, MA 02139, USA','School of Computing. E-mail: author@example.org']
        self.assertEqual(clean_institutions(values,['Nicolas Ballas']),[
            'Courant Institute, New York University','National University of Singapore',
            'University of Oxford','School of Computing'])
        self.assertEqual(clean_institutions([
            'California Institute of Technology, CA 91125, USA',
            'New York University, NY 10012, USA',
            'This work is supported by The Dow Chemical Company project #227027AW.',
            'London, EC2A 4DQ',
            'The authors are with the University of California, Berkeley.']),
            ['California Institute of Technology','New York University',
             'University of California, Berkeley'])

    def test_arxiv_fallback_ignores_project_links_and_numbered_names(self):
        paper={**self.paper(),'arxiv_id':'2610.42148v1','authors':['Bobo Li']}
        html='''<div class="ltx_authors"><span>Bobo Li</span>
        <span class="ltx_role_affiliation">1National University of Singapore2University of Oxford</span>
        <span>National University of Singapore</span><span>University of Oxford</span>
        <span class="ltx_role_affiliation">Project Page:https://flide.org</span>
        <span class="ltx_role_affiliation">Source Code:https://github.com/example</span></div>'''
        response=type('Response',(),{'text':html,'raise_for_status':lambda self:None})()
        with patch('research_affiliations._verify_source',return_value=True), patch('research_affiliations._lookup',return_value=None), patch('research_affiliations.requests.get',return_value=response), patch('research_affiliations.time.sleep'):
            enrich_affiliations([paper])
        self.assertEqual(paper['institutions'],['National University of Singapore','University of Oxford'])

    def test_site_hides_legacy_affiliation_artifacts_before_publication(self):
        paper={'key':'paper:'+'a'*24,'url':'https://arxiv.org/abs/2610.42148v1',
               'original_headline':'Verified AI paper','publisher':'arXiv','date':'2026-10-30',
               'authors':['Bobo Li'],'institutions':['Project Page:https://flide.org',
                   'National University of Singapore','University of Oxford']}
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'data/research/public.json'
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({'papers':[paper]}))
            with patch.object(build_site,'ROOT',Path(directory)):
                rendered=build_site.papers()
        self.assertEqual(rendered[0]['institutions'],['National University of Singapore','University of Oxford'])


if __name__=='__main__':
    unittest.main()
