from pathlib import Path
import copy
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from weekly_editorials import (apply_editorials, validate_draft, validate_section,
                               news_selection, research_selection, eligible, art_candidates, CHECKS)
from weekly_overviews import prepare_weekly_overviews
from check_observatory_update import needs_weekly_review


class WeeklyEditorialTests(unittest.TestCase):
    def setUp(self):
        logger = patch('weekly_editorials.print', create=True)
        logger.start()
        self.addCleanup(logger.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.release = {'release_id': '2026-W41', 'period_start': '2026-10-05', 'period_end': '2026-10-11'}
        self.news = [self.row('news'+str(i), market=code) for i, code in enumerate(('US','CA','CN','FR','GB'))]
        self.papers = [self.row('paper'+str(i), paper=True) for i in range(2)]
        art = []
        for i in range(8):
            path = 'assets/culture/picture'+str(i)+'.jpg'
            (self.root/path).parent.mkdir(parents=True, exist_ok=True)
            (self.root/path).write_bytes(b'fixture')
            art.append({'key': 'picture'+str(i), 'image_path': path, 'headline': 'A bridge over water '+str(i),
                        'creator': 'An artist', 'publisher': 'A museum', 'source_url': 'https://museum.example/work/'+str(i),
                        'rights': {'label': 'CC0 image'}})
        (self.root/'data/culture').mkdir(parents=True)
        (self.root/'data/culture/library-art.json').write_text(json.dumps(art))
        self.calls = []

    def row(self, key, market='', paper=False):
        return {'key': key, 'headline': 'Testing reliable answers in math tasks',
                'deck': 'Checking answers helps find errors but wider tests are still needed.',
                'what_happened': 'Researchers checked reliable answers in math tasks.',
                'limitation': 'Only math tasks were tested.', 'has_editorial': True,
                'date': '2026-10-07', 'path': ('research/' if paper else 'story/')+key+'/index.html',
                'url': 'https://example.org/'+key, 'markets': [market] if market else [],
                'sources': [{'url': 'https://example.org/'+key}], 'publisher': 'A source',
                'research_label': 'Preprint', 'summary_basis': 'Summary of the abstract'}

    def call(self, prompt, **kwargs):
        self.calls.append(kwargs['stage'])
        if kwargs['stage'] == 'weekly_review':
            return dict.fromkeys(CHECKS, True)
        payload = json.loads(prompt.split('\n')[-2] if prompt.endswith('\n') else prompt.split('\n')[-1])
        parts = [{'text': 'What I notice this week is the value of asking how an answer was checked. A promising result gives us a starting point, but it does not settle every question.', 'source_key': ''}]
        for row in payload['sources']:
            parts.append({'text': 'This work on checking answers', 'source_key': row['key']})
            parts.append({'text': 'shows why careful testing matters.', 'source_key': ''})
        return {'title': 'A closer look at the answers', 'paragraphs': [parts, [
            {'text': 'The findings remain limited to the tasks tested. Before we trust a confident answer in daily life, what would help us see where it might still go wrong?', 'source_key': ''}]],
            'image_key': payload['artworks'][0]['key'], 'image_reason': 'A bridge suggests the careful steps between a promising finding and everyday trust.'}

    def generate(self, history=None, call=None):
        current, _ = prepare_weekly_overviews(self.news, self.papers, self.release, self.root)
        return apply_editorials(current, self.news, self.papers, self.root, history or [], allow_model=True, call=call or self.call)

    def test_signed_prose_exact_sources_limits_and_distinct_images(self):
        result = self.generate()
        self.assertEqual(result['editorial_status'], 'ready')
        self.assertEqual(self.calls, ['weekly_draft','weekly_review']*2)
        self.assertNotEqual(result['markets']['image_path'], result['research']['image_path'])
        for kind, count in (('markets',5), ('research',2)):
            section = result[kind]
            validate_section(section)
            self.assertEqual(section['author'], 'Kedma Hamelberg')
            self.assertLessEqual(section['word_count'], 200)
            self.assertEqual(len(section['source_hashes']), count)
            self.assertNotRegex(section['title']+' '+section['summary'], '[:\u2013\u2014]')

    def test_cached_prose_does_not_change_on_daily_rebuild(self):
        first = self.generate()
        self.news.reverse()
        def never(*args, **kwargs):
            self.fail('A completed review must not call the model again')
        second = self.generate([first], call=never)
        self.assertEqual(first, second)

    def test_next_week_uses_new_art_and_old_archive_is_unchanged(self):
        first = self.generate()
        saved = copy.deepcopy(first)
        self.release.update(release_id='2026-W42', period_start='2026-10-12', period_end='2026-10-18')
        for row in self.news+self.papers: row['date'] = '2026-10-14'
        second = self.generate([first])
        paths = [x[kind]['image_path'] for x in (first,second) for kind in ('markets','research')]
        self.assertEqual(len(set(paths)),4)
        self.assertEqual(first,saved)

    def test_missing_market_or_second_paper_is_pending_without_byline(self):
        self.news.pop()
        self.papers[1]['date'] = '2026-10-12'
        result = self.generate()
        self.assertEqual(self.calls, [])
        for kind in ('markets','research'):
            self.assertEqual(result[kind]['status'], 'pending')
            self.assertNotIn('author', result[kind])

    def test_overlapping_markets_use_five_different_stories(self):
        self.news[0]['markets'] = ['US','CA']
        result = news_selection(self.news)
        self.assertEqual(len({x['key'] for x in result}),5)
        self.assertEqual({x['selected_market'] for x in result}, {'US','CA','CN','FR','GB'})

    def test_related_pair_and_date_filter(self):
        unrelated = self.row('unrelated',paper=True)
        unrelated.update(headline='Fossil pollen',deck='Ecological vegetation grasslands',what_happened='Ancient plant ecosystems')
        self.assertEqual({x['key'] for x in research_selection(self.papers+[unrelated])}, {'paper0','paper1'})
        self.papers[0]['date']='2026-10-04'
        self.assertEqual(len(eligible(self.papers,self.release)),1)

    def test_two_versions_of_one_paper_do_not_make_a_pair(self):
        self.papers[0]['url']='https://arxiv.org/abs/2610.12345v1'
        self.papers[1]['url']='https://arxiv.org/abs/2610.12345v2'
        self.assertEqual(research_selection(self.papers),[])

    def test_duplicate_catalog_records_do_not_reuse_the_same_artwork(self):
        path=self.root/'data/culture/library-art.json'
        catalog=json.loads(path.read_text())
        duplicate={**catalog[0],'key':'duplicate','image_path':catalog[1]['image_path']}
        path.write_text(json.dumps(catalog+[duplicate]))
        choices=art_candidates(self.root,[],self.news,'2026-W41','markets')
        self.assertEqual(len(choices),8)
        first=self.generate()
        later=art_candidates(self.root,[first],self.news,'2026-W42','markets')
        self.assertTrue(all(a['image_work_key'] not in {first[k]['image_work_key'] for k in ('markets','research')} for a in later))

    def test_preview_does_not_reset_retry_count(self):
        first=self.generate(call=lambda *a,**k: (_ for _ in ()).throw(ValueError('fixture failure')))
        current,_=prepare_weekly_overviews(self.news,self.papers,self.release,self.root)
        second=apply_editorials(current,self.news,self.papers,self.root,[first],allow_model=False)
        self.assertEqual(second['markets']['attempts'],1)

    def test_rejected_review_is_not_published_and_retry_is_bounded(self):
        def reject(prompt, **kwargs):
            return dict.fromkeys(CHECKS,False) if kwargs['stage']=='weekly_review' else self.call(prompt,**kwargs)
        previous=[]
        for expected in range(1,4):
            result=self.generate(previous,call=reject)
            self.assertEqual(result['markets']['attempts'],expected)
            self.assertNotIn('author',result['markets'])
            previous=[result]
        self.assertFalse(needs_weekly_review(self.release,{'weekly_overview':result}))
        fourth=self.generate(previous,call=lambda *a,**k:self.fail('Retry cap exceeded'))
        self.assertEqual(fourth['markets']['pending_reason'],'review_needs_attention')

    def test_old_week_is_not_rewritten_in_new_voice(self):
        self.release.update(release_id='2026-W40',period_start='2026-09-28',period_end='2026-10-04')
        result=self.generate()
        self.assertNotIn('editorial_version',result)
        self.assertEqual(self.calls,[])

    def test_punctuation_missing_link_and_invented_number_are_rejected(self):
        good=self.generate()['markets']
        draft={'title':good['title'],'paragraphs':[[{k:p[k] for k in ('text','source_key')} for p in paragraph] for paragraph in good['prose']], 'image_key':good['image_key'],'image_reason':good['image_reason']}
        for title in ('A title with a colon here:', 'A title with an en dash – here', 'A gain of 987654'):
            broken={**draft,'title':title}
            with self.assertRaises(ValueError):validate_draft(broken,self.news,[{'key':good['image_key']}])
        broken=copy.deepcopy(draft)
        broken['paragraphs'][0][1]['source_key']=''
        with self.assertRaises(ValueError):validate_draft(broken,self.news,[{'key':good['image_key']}])


if __name__ == '__main__':
    unittest.main()
