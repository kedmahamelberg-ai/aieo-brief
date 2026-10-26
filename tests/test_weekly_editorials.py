from pathlib import Path
import copy
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from weekly_editorials import (apply_editorials, validate_draft, validate_section,
                               validate_citation_alignment, validate_public_weekly_sources,
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
        later_week = bool(payload.get('recent_style', {}).get('openings'))
        opening = ('A careful test can reveal where a confident answer falls short.' if later_week else
                   'A promising result gives us a starting point, but it does not settle every question.')
        parts = [{'text': opening, 'source_key': ''}]
        for row in payload['sources']:
            parts.append({'text': 'This work on checking answers', 'source_key': row['key']})
            parts.append({'text': 'shows why careful testing matters.', 'source_key': ''})
        return {'title': 'Careful checks before trust' if later_week else 'A closer look at the answers',
                'paragraphs': [parts, [
            {'text': ('The findings remain limited to the tasks tested. That gives us a useful reason to ask how an answer was checked.' if later_week else
                      'The findings remain limited to the tasks tested. Before we trust a confident answer in daily life, what would help us see where it might still go wrong?'), 'source_key': ''}]],
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
        self.assertNotEqual(first['markets']['title'], second['markets']['title'])
        self.assertNotEqual(first['markets']['prose'][0][0]['text'], second['markets']['prose'][0][0]['text'])

    def test_stock_opening_repeated_opening_and_multiple_questions_are_rejected(self):
        section = self.generate()['markets']
        draft = {'title': section['title'], 'paragraphs': [[{k: part[k] for k in ('text', 'source_key')}
                 for part in paragraph] for paragraph in section['prose']],
                 'image_key': section['image_key'], 'image_reason': section['image_reason']}
        stock = copy.deepcopy(draft)
        stock['paragraphs'][0][0]['text'] = 'What I noticed this week is that careful checking matters.'
        with self.assertRaisesRegex(ValueError, 'weekly_stock_opening'):
            validate_draft(stock, self.news, [{'key': section['image_key']}], enforce_style=True)
        with self.assertRaisesRegex(ValueError, 'weekly_repeated_opening'):
            validate_draft(draft, self.news, [{'key': section['image_key']}],
                           [section['prose'][0][0]['text']], enforce_style=True)
        with self.assertRaisesRegex(ValueError, 'weekly_too_many_questions'):
            validate_draft({**draft, 'title': 'How do we check an answer?'},
                           self.news, [{'key': section['image_key']}], enforce_style=True)
        with self.assertRaisesRegex(ValueError, 'weekly_question_repeated_next_week'):
            validate_draft(draft, self.news, [{'key': section['image_key']}],
                           enforce_style=True, questions_allowed=False)

    def test_old_checked_weekly_prose_remains_valid_after_style_change(self):
        history = json.loads((Path(__file__).resolve().parents[1] /
                              'data/weekly-overviews/history.json').read_text())['overviews']
        old = next(item for item in history if item['release_id'] == '2026-W43')
        self.assertTrue(old['markets']['summary'].startswith('What I notice'))
        validate_section(old['markets'])

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
            return dict.fromkeys(CHECKS,False) if kwargs['stage'] in ('weekly_review','weekly_review_repeat') else self.call(prompt,**kwargs)
        previous=[]
        for expected in range(1,4):
            result=self.generate(previous,call=reject)
            self.assertEqual(result['markets']['attempts'],expected)
            self.assertNotIn('author',result['markets'])
            previous=[result]
        self.assertFalse(needs_weekly_review(self.release,{'weekly_overview':result}))
        fourth=self.generate(previous,call=lambda *a,**k:self.fail('Retry cap exceeded'))
        self.assertEqual(fourth['markets']['pending_reason'],'review_needs_attention')

    def test_failed_independent_review_requires_a_new_checked_revision(self):
        attempts = []
        def correct(prompt, **kwargs):
            attempts.append(kwargs['stage'])
            if kwargs['stage'] == 'weekly_review':
                return {name: name != 'grounded' for name in CHECKS}
            if kwargs['stage'] == 'weekly_review_repeat':
                return dict.fromkeys(CHECKS, True)
            return self.call(prompt, **kwargs)
        result = self.generate(call=correct)
        self.assertEqual(result['editorial_status'], 'ready')
        self.assertEqual(attempts.count('weekly_review_repair'), 2)
        self.assertEqual(attempts.count('weekly_review_repeat'), 2)
        self.assertTrue(all(result[k]['review_checks']['grounded'] for k in ('markets','research')))

    def test_malformed_inline_part_gets_targeted_bounded_repairs(self):
        stages = []
        def repair(prompt, **kwargs):
            stage = kwargs['stage']
            stages.append(stage)
            draft = self.call(prompt, **kwargs)
            if stage == 'weekly_review':
                return draft
            if stage in ('weekly_draft', 'weekly_repair'):
                draft['paragraphs'][0][0]['text'] = ''
            if stage == 'weekly_repair':
                self.assertIn('paragraph 1, part 1: text must be a nonempty string', prompt)
            return draft
        result = self.generate(call=repair)
        self.assertEqual(result['editorial_status'], 'ready')
        self.assertEqual(stages.count('weekly_repair_final'), 2)
        self.assertEqual(stages.count('weekly_review'), 2)

    def test_repeated_malformed_part_never_reaches_independent_review(self):
        stages = []
        def malformed(prompt, **kwargs):
            stage = kwargs['stage']
            stages.append(stage)
            draft = self.call(prompt, **kwargs)
            if stage == 'weekly_review':
                return draft
            draft['paragraphs'][0][0]['text'] = ''
            return draft
        result = self.generate(call=malformed)
        self.assertEqual(result['editorial_status'], 'pending')
        self.assertEqual(stages.count('weekly_repair_final'), 2)
        self.assertNotIn('weekly_review', stages)
        self.assertEqual(result['research']['last_error'],
                         'weekly_part: paragraph 1, part 1: text must be a nonempty string')

    def test_new_format_revision_retries_an_exhausted_older_draft(self):
        """A changed editorial brief must supersede a prior retry cap.

        This protects format corrections such as a new word cap, plain-language
        requirement, source selection rule, or artwork rule.  Those corrections
        need a fresh checked draft rather than the earlier placeholder.
        """
        def reject(prompt, **kwargs):
            return dict.fromkeys(CHECKS, False) if kwargs['stage'] in ('weekly_review','weekly_review_repeat') else self.call(prompt, **kwargs)

        previous = []
        for _ in range(3):
            previous = [self.generate(previous, call=reject)]
        for section in ('markets', 'research'):
            previous[0][section]['editorial_version'] = 'kedma-weekly-v1'
            previous[0][section]['attempts'] = 3
            previous[0][section]['pending_reason'] = 'review_needs_attention'
            previous[0][section]['input_hash'] = 'v1-input-hash'

        recovered = self.generate(previous)
        self.assertEqual(recovered['editorial_status'], 'ready')
        for section in ('markets', 'research'):
            self.assertEqual(recovered[section]['editorial_version'], 'kedma-weekly-v10')
            self.assertLessEqual(recovered[section]['word_count'], 200)

    def test_old_week_is_not_rewritten_in_new_voice(self):
        self.release.update(release_id='2026-W40',period_start='2026-09-28',period_end='2026-10-04')
        result=self.generate()
        self.assertNotIn('editorial_version',result)
        self.assertEqual(self.calls,[])

    def test_natural_punctuation_is_accepted_but_missing_links_and_invented_numbers_are_rejected(self):
        good=self.generate()['markets']
        draft={'title':good['title'],'paragraphs':[[{k:p[k] for k in ('text','source_key')} for p in paragraph] for paragraph in good['prose']], 'image_key':good['image_key'],'image_reason':good['image_reason']}
        natural={**draft,'title':'A title with a colon: and an en dash – naturally'}
        validate_draft(natural,self.news,[{'key':good['image_key']}])
        broken={**draft,'title':'A gain of 987654'}
        with self.assertRaises(ValueError):validate_draft(broken,self.news,[{'key':good['image_key']}])
        broken=copy.deepcopy(draft)
        broken['paragraphs'][0][1]['source_key']=''
        with self.assertRaises(ValueError):validate_draft(broken,self.news,[{'key':good['image_key']}])

    def test_short_citation_markers_restore_exact_saved_source_keys(self):
        prompts = []
        def marked(prompt, **kwargs):
            if kwargs['stage'] == 'weekly_draft':
                payload = json.loads(prompt.split('\n')[-1])
                prompts.append(payload['sources'])
            return self.call(prompt, **kwargs)
        result = self.generate(call=marked)
        self.assertEqual(result['editorial_status'], 'ready')
        self.assertEqual([row['key'] for row in prompts[0]],
                         ['sourceA', 'sourceB', 'sourceC', 'sourceD', 'sourceE'])
        for kind, rows in (('markets', self.news), ('research', self.papers)):
            linked = [part['source_key'] for paragraph in result[kind]['prose']
                      for part in paragraph if part['source_key']]
            self.assertEqual(sorted(linked), sorted(row['key'] for row in rows))
            self.assertTrue(all(part['path'].startswith(('story/', 'research/'))
                                for paragraph in result[kind]['prose'] for part in paragraph
                                if part['source_key']))

    def test_short_artwork_markers_restore_eligible_catalog_choice(self):
        seen_artworks = []
        def marked(prompt, **kwargs):
            if kwargs['stage'] == 'weekly_draft':
                payload = json.loads(prompt.split('\n')[-1])
                seen_artworks.append(payload['artworks'])
            return self.call(prompt, **kwargs)
        result = self.generate(call=marked)
        self.assertEqual(result['editorial_status'], 'ready')
        self.assertEqual(seen_artworks[0][0]['key'], 'artAA')
        catalog = json.loads((self.root/'data/culture/library-art.json').read_text())
        eligible_keys = {row['key'] for row in catalog}
        for kind in ('markets', 'research'):
            self.assertIn(result[kind]['image_key'], eligible_keys)
            self.assertNotIn(result[kind]['image_key'], {row['key'] for row in seen_artworks[0]})

    def test_ineligible_artwork_marker_stays_blocked_with_precise_feedback(self):
        draft = self.call(json.dumps({'sources': [{'key': 'sourceA'}, {'key': 'sourceB'}],
                                      'artworks': [{'key': 'artAA'}]}), stage='weekly_draft')
        draft['image_key'] = 'not-an-artwork'
        with self.assertRaisesRegex(ValueError, 'weekly_image_not_eligible: choose one of artAA'):
            validate_draft(draft, [{'key': 'sourceA'}, {'key': 'sourceB'}],
                           [{'key': 'artAA'}])

    def test_missing_citation_feedback_names_the_marker(self):
        draft = self.call(json.dumps({'sources': [{'key': 'sourceA'}, {'key': 'sourceB'}],
                                      'artworks': [{'key': 'picture0'}]}), stage='weekly_draft')
        draft['paragraphs'][0] = [part for part in draft['paragraphs'][0]
                                  if part['source_key'] != 'sourceB']
        with self.assertRaisesRegex(ValueError, 'missing sourceB'):
            validate_draft(draft, [{'key': 'sourceA'}, {'key': 'sourceB'}],
                           [{'key': 'picture0'}])

    def test_length_feedback_gives_the_count_and_source_titles_are_saved(self):
        good = self.generate()['markets']
        self.assertTrue(all(entry['story']['headline'] for entry in good['entries']))
        self.assertTrue(all(entry['story']['publisher'] for entry in good['entries']))
        draft = {'title': ' '.join(['Very long title'] * 80),
                 'paragraphs': [[{k: part[k] for k in ('text', 'source_key')}
                                 for part in paragraph] for paragraph in good['prose']],
                 'image_key': good['image_key'], 'image_reason': good['image_reason']}
        with self.assertRaisesRegex(ValueError, r'weekly_length: \d+ words'):
            validate_draft(draft, self.news, [{'key': good['image_key']}])
        changed = copy.deepcopy(good)
        changed['entries'][0]['story']['path'] = 'story/another/index.html'
        with self.assertRaisesRegex(ValueError, 'source list does not match'):
            validate_section(changed)

    def test_source_markers_cannot_appear_in_visible_prose(self):
        good = self.generate()['markets']
        draft = {'title': good['title'],
                 'paragraphs': [[{k: part[k] for k in ('text', 'source_key')}
                                 for part in paragraph] for paragraph in good['prose']],
                 'image_key': good['image_key'], 'image_reason': good['image_reason']}
        draft['paragraphs'][0][0]['text'] += ' See sourceA.'
        with self.assertRaisesRegex(ValueError, 'weekly_citation_marker_in_text'):
            validate_draft(draft, self.news, [{'key': good['image_key']}])
        draft['paragraphs'][0][0]['text'] = 'See paper:214dec5532c4cb3bfe817fe3.'
        with self.assertRaisesRegex(ValueError, 'weekly_citation_marker_in_text'):
            validate_draft(draft, self.news, [{'key': good['image_key']}])

    def test_contractions_are_rejected_but_possessives_remain_valid(self):
        good = self.generate()['markets']
        draft = {'title': good['title'],
                 'paragraphs': [[{k: p[k] for k in ('text', 'source_key')} for p in paragraph]
                                for paragraph in good['prose']],
                 'image_key': good['image_key'], 'image_reason': good['image_reason']}
        for title in ("What's next for learning", "What’s next for learning"):
            with self.assertRaisesRegex(ValueError, 'weekly_contraction'):
                validate_draft({**draft, 'title': title}, self.news,
                               [{'key': good['image_key']}])
        prose = copy.deepcopy(draft)
        prose['paragraphs'][0][0]['text'] += " We don't know every effect."
        with self.assertRaisesRegex(ValueError, 'weekly_contraction'):
            validate_draft(prose, self.news, [{'key': good['image_key']}])
        with self.assertRaisesRegex(ValueError, 'weekly_contraction'):
            validate_draft({**draft, 'image_reason': "It's a bridge between ideas."},
                           self.news, [{'key': good['image_key']}])
        validate_draft({**draft, 'title': "This Week’s Learning Review"}, self.news,
                       [{'key': good['image_key']}])

    def test_human_approved_edition_is_used_without_calling_model(self):
        generated = self.generate()
        approval = {"release_id": self.release['release_id'], "human_approved_at": "2026-10-12T00:00:00Z"}
        for kind in ('markets', 'research'):
            approval[kind] = copy.deepcopy(generated[kind])
            approval[kind]['human_approved'] = True
        path = self.root/'data/weekly-overviews/approved'
        path.mkdir(parents=True)
        (path/(self.release['release_id']+'.json')).write_text(json.dumps(approval))
        current, _ = prepare_weekly_overviews(self.news, self.papers, self.release, self.root)
        result = apply_editorials(current, self.news, self.papers, self.root, [], allow_model=True,
                                  call=lambda *a, **k: self.fail('Human approval must not call the model'))
        self.assertTrue(result['markets']['human_approved'])
        self.assertTrue(result['research']['human_approved'])

    def test_citation_cannot_describe_another_selected_story(self):
        sources = [
            {'key': 'ca', 'headline': 'Canadian grant for soybean and barley varieties',
             'deck': 'Regional cultivar development in Eastern Canada will accelerate local crop research.'},
            {'key': 'us', 'headline': 'American parents discuss artificial intelligence with children',
             'deck': 'Families ask how to handle curious questions and practical cautions.'},
        ]
        prose = [[{'text': 'The regional project aims to accelerate local cultivar development.',
                   'source_key': 'us'}]]
        with self.assertRaisesRegex(ValueError, 'weekly_citation_source_mismatch'):
            validate_citation_alignment(prose, sources)
        prose[0][0]['source_key'] = 'ca'
        validate_citation_alignment(prose, sources)

    def test_approved_source_survives_public_slug_only_with_reachable_legacy_link(self):
        generated = self.generate()
        approval = {'release_id': self.release['release_id'],
                    'human_approved_at': '2026-10-12T00:00:00Z'}
        for kind in ('markets', 'research'):
            approval[kind] = copy.deepcopy(generated[kind])
            approval[kind]['human_approved'] = True
        path = self.root/'data/weekly-overviews/approved'
        path.mkdir(parents=True)
        (path/(self.release['release_id']+'.json')).write_text(json.dumps(approval))
        public_news, public_research = copy.deepcopy(self.news), copy.deepcopy(self.papers)
        for row in public_news + public_research:
            old_path = row['path']
            row['path'] = old_path.replace('/index.html', '-readable/index.html')
            row['legacy_paths'] = [old_path]
        overview, _ = prepare_weekly_overviews(public_news, public_research,
                                                self.release, self.root,
                                                source_news=self.news,
                                                source_research=self.papers)
        self.assertEqual(overview['editorial_status'], 'ready')
        validate_public_weekly_sources(overview, self.news, self.papers,
                                       public_news, public_research)
        public_news[0]['legacy_paths'] = []
        with self.assertRaisesRegex(ValueError, 'weekly_public_link_missing'):
            validate_public_weekly_sources(overview, self.news, self.papers,
                                           public_news, public_research)
        public_news[0]['legacy_paths'] = [self.news[0]['path']]
        public_news[0]['deck'] = 'A substantively different claim'
        with self.assertRaisesRegex(ValueError, 'weekly_public_source_changed'):
            validate_public_weekly_sources(overview, self.news, self.papers,
                                           public_news, public_research)


if __name__ == '__main__':
    unittest.main()
