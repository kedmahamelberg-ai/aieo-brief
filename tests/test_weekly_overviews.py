from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

from weekly_overviews import prepare_weekly_overviews, social_queue
from research_affiliations import enrich_affiliations


class WeeklyOverviewTests(unittest.TestCase):
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


if __name__=='__main__':
    unittest.main()
