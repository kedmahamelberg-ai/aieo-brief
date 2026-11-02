"""Regression coverage for the 7 September draft-generation failure.

All model and database traffic is mocked. These tests never send a request,
publish content, or use account credentials.
"""
import copy
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import ExitStack, redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import requests
import editorial_engine as engine
import generate_editorial_stories as news
import generate_research_summaries as research


def fixture():
    source = ('Researchers surveyed 142 musicians about AI. '
              'A large majority raised concerns about payment. '
              'The survey cannot represent every musician.')
    draft = {
        'editorial_headline': 'Musician survey highlights concern about AI and income',
        'editorial_deck': 'Respondents describe worries about how their work is valued.',
        'what_happened': 'A survey asked 142 music professionals about AI.',
        'why_it_matters': 'The responses raise questions about fair payment.',
        'for_humans': 'Participants describe concerns.',
        'for_ai': '',
        'body_paragraphs': ['The findings describe what respondents said, with limits on wider conclusions.'],
        'claim_status': 'study',
        'limitation': 'Only the abstract was read; this preprint has not been peer reviewed.',
        'support': [{'field': field, 'source_number': 1,
                     'quote': 'A large majority raised concerns about payment.'}
                    for field in engine.SUPPORT_FIELDS],
    }
    return draft, [{'source_number': 1, 'headline': 'Musician study', 'evidence': source}]


def accepted_review(draft=None):
    default, sources = fixture()
    draft = draft or default
    return {**dict.fromkeys(engine.REVIEW_CHECKS + engine.claim_grounding.CHECKS, True), 'reason': 'Supported.',
            'field_reviews': [{'field': key, 'verdict': 'supported', 'reason': 'Test verifier fixture.',
                               'citations': [{'source_number': 1, 'quote': sources[0]['evidence'][:42]}]}
                              for key in engine.claim_grounding.units(draft)]}


class EditorialRecovery(unittest.TestCase):
    def test_repair_selection_prioritizes_missing_public_summary(self):
        missing='00000000-0000-0000-0000-000000000001'
        current='00000000-0000-0000-0000-000000000002'
        release={'evidence':[{'event_id':missing,'event_date':'2026-10-22'},
                             {'event_id':current,'event_date':'2026-10-22'}],
                 'complete_content':False,'content_sha256':'edition','release_id':'2026-W43'}
        sym={'evidence':[{'event_id':missing},{'event_id':current}]}
        versions={'missing':{'story_version_id':'old','publication_status':'preview'},
                  'current':{'story_version_id':'new','publication_status':'preview'}}
        maps=({missing:{'story_id':'missing'},current:{'story_id':'current'}},{}, {},versions)
        source={'source_number':1,'publisher':'Source','headline':'Article','evidence':'Complete source text.'}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'data/editorial').mkdir(parents=True)
            (root/'data/editorial/retry-state.json').write_text(json.dumps({missing:{'attempts':5}}))
            with patch.object(news,'ROOT',root),patch.object(news,'corrections',return_value={}),patch.object(news,'fixed_relationship',return_value={'axes':{'evidence_complete':True}}),patch.object(news,'source_payload',return_value=[source]),patch.object(news,'fingerprint',side_effect=lambda e,*_:e['event_id']),patch.object(news,'version_valid',side_effect=lambda _v,_r,_l,e,_p:e['event_id']==current):
                selected,_,_=news.candidates(release,sym,maps)
        self.assertEqual([item['eid'] for item in selected],[missing,current])

    def test_targeted_news_repair_rejects_unknown_ids(self):
        eid='00000000-0000-0000-0000-000000000001'
        other='00000000-0000-0000-0000-000000000002'
        release={'evidence':[{'event_id':eid},{'event_id':other}]}
        items=[{'eid':other},{'eid':eid}]
        self.assertEqual(news.select_event_ids(items,eid,release),[items[1]])
        with self.assertRaisesRegex(ValueError,'not in the completed edition'):
            news.select_event_ids(items,'00000000-0000-0000-0000-000000000003',release)
        with self.assertRaisesRegex(ValueError,'no pending source-ready draft'):
            news.select_event_ids([items[1]],other,release)

    def test_source_digits_allow_equivalent_thousands_grouping(self):
        self.assertIn('12,000',engine.source_numeric_aliases('近12000名新生'))
        self.assertNotIn('12,000',engine.source_numeric_aliases('近12000%'))

    def test_news_seed_requires_exact_source_hash(self):
        eid='00000000-0000-0000-0000-000000000001'
        event={'event_id':eid,'event_title':'Source title','event_date':'2026-10-22'}
        release={'evidence':[event],'complete_content':False,'content_sha256':'edition'}
        sym={'evidence':[{'event_id':eid}]}
        source={'source_number':1,'publisher':'Source','headline':'Source title','evidence':'Complete article text.','quality':{'body_sha256':'matching-hash'}}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'data/editorial').mkdir(parents=True)
            (root/'data/editorial/news-seeds.json').write_text(json.dumps({'seeds':{eid:{'evidence_sha256':['matching-hash'],'draft':{'editorial_headline':'Checked title'}}}}))
            with patch.object(news,'ROOT',root),patch.object(news,'fixed_relationship',return_value={'axes':{'evidence_complete':True}}),patch.object(news,'source_payload',return_value=[source]):
                selected,_,_=news.candidates(release,sym,({}, {},{},{}))
                self.assertEqual(selected[0]['event']['draft_seed']['editorial_headline'],'Checked title')
                source['quality']['body_sha256']='changed-hash'
                selected,_,_=news.candidates(release,sym,({}, {},{},{}))
                self.assertNotIn('draft_seed',selected[0]['event'])

    def test_video_caption_uses_verified_official_transcript(self):
        from source_evidence_quality import assess_body
        caption='10月19日，工业和信息化部介绍人工智能产业情况。\n新华社音视频部制作'
        self.assertIn('video_caption_only',assess_body({'body_text':caption,'content_basis':'full_source'})['flags'])
        eid='ce676615-712f-46c1-97be-74ff29ea8bc2'
        supplement=json.loads((ROOT/'data/editorial/source-supplements.json').read_text())['sources'][eid]
        import hashlib
        self.assertEqual(hashlib.sha256(supplement['evidence_text'].encode()).hexdigest(),supplement['evidence_sha256'])
        self.assertTrue(assess_body({'body_text':supplement['evidence_text'],'content_basis':'full_source'})['usable_complete_body'])

    def test_publisher_template_is_not_complete_source_evidence(self):
        from source_evidence_quality import assess_body
        template='{{summary}}\n来源：上观新闻\n作者：{{author}}\n{{brTitle}}\n{{editorLabel}}：{{maineditor}}\n此文章不存在或已下线'
        quality=assess_body({'body_text':template,'content_basis':'full_source'})
        self.assertIn('unrendered_or_unavailable_source',quality['flags'])
        self.assertFalse(quality['usable_complete_body'])
        valid='This original article reports on an AI governance forum and describes the statements of several speakers. '*10
        self.assertTrue(assess_body({'body_text':valid+' Example {{template}}','content_basis':'full_source'})['usable_complete_body'])
        navigation='郑重声明：东方财富发布此内容旨在传播更多信息。热点阅读\n'+('市场新闻与排行。'*15)+'\n打开东方财富APP查看更多内容\n点击查看更多内容'
        self.assertIn('article_navigation_only',assess_body({'body_text':navigation,'content_basis':'full_source'})['flags'])

    def test_verified_copy_requires_the_exact_published_body_hash(self):
        from source_supplements import verified_text
        import hashlib
        body=('A university published the full attributed article with methods and source context. '*8).strip()
        markup=('<div class="v_news_content"><p>'+body+'</p></div>').encode()
        response=Mock(content=markup)
        response.raise_for_status.return_value=None
        supplement={'source_url':'https://www.ecnu.edu.cn/info/example.htm',
                    'evidence_sha256':hashlib.sha256(body.encode()).hexdigest()}
        self.assertEqual(verified_text(supplement,get=lambda *a,**k:response),body)
        self.assertEqual(verified_text({**supplement,'evidence_sha256':'0'*64},get=lambda *a,**k:response),'')
        self.assertEqual(verified_text({**supplement,'source_url':'https://evil.example/story'},get=lambda *a,**k:response),'')

    def test_headline_correction_does_not_lock_missing_summary(self):
        eid='b7cc7093-b0e0-4f9b-9d7a-1469436f671f'
        event={'event_id':eid,'event_title':'Ustar Technology researches physical AI','event_date':'2026-10-23'}
        release={'evidence':[event],'complete_content':False,'content_sha256':'edition'}
        sym={'evidence':[{'event_id':eid}]}
        relation={'axes':{'evidence_complete':True}}
        source={'source_number':1,'publisher':'Source','headline':'Unitree research','evidence':'The company describes preliminary research on physical AI.'}
        with tempfile.TemporaryDirectory() as directory,patch.object(news,'ROOT',Path(directory)),patch.object(news,'is_locked',return_value=True),patch.object(news,'corrections',return_value={'event:'+eid:{'headline':'Unitree researches physical AI'}}),patch.object(news,'fixed_relationship',return_value=relation),patch.object(news,'source_payload',return_value=[source]):
            selected,counts,_=news.candidates(release,sym,({}, {},{},{}))
            self.assertEqual(counts['needs_model'],1)
            self.assertEqual(selected[0]['event']['event_title'],'Unitree researches physical AI')
            existing={'s':{'story_version_id':'v','publication_status':'preview'}}
            selected,counts,_=news.candidates(release,sym,({eid:{'story_id':'s'}},{},{},existing))
            self.assertEqual(selected,[])

    def test_research_readability_edit_is_checked_against_original_source(self):
        draft,sources=fixture()
        technical=copy.deepcopy(draft)
        technical['editorial_headline']='Native RL highlights musician concerns'
        edited={k:v for k,v in draft.items() if k!='support'}
        with patch.object(engine,'call_json',side_effect=[technical,edited,accepted_review()]) as model:
            result,_=engine.write_story({}, {}, sources, kind='paper')
        self.assertEqual(result['editorial_headline'],draft['editorial_headline'])
        self.assertEqual(model.call_args_list[1].kwargs['stage'],'reading_level')
        self.assertEqual(model.call_args_list[2].kwargs['stage'],'scope_review')
        self.assertIn(sources[0]['evidence'],model.call_args_list[2].args[0])

    def test_editorial_seed_still_requires_validation_and_scope_review(self):
        draft, sources = fixture()
        with patch.object(engine, 'call_json', return_value=accepted_review()) as model:
            result, proof = engine.write_story({'draft_seed': draft}, {}, sources, kind='preprint')
        self.assertEqual(result['what_happened'], draft['what_happened'])
        self.assertEqual(proof['draft_origin'], 'reviewed_editorial_seed')
        self.assertEqual(model.call_args.kwargs['stage'], 'scope_review')
        bad = copy.deepcopy(draft)
        bad['what_happened'] = 'The study included 999 people.'
        with patch.object(engine, 'call_json', side_effect=[draft, accepted_review()]) as model:
            result, proof = engine.write_story({'draft_seed': bad}, {}, sources, kind='preprint')
        self.assertEqual(result['what_happened'], draft['what_happened'])
        self.assertEqual(proof['draft_origin'], 'model')

    def test_news_removes_only_named_unsupported_paragraph_then_rechecks_all_fields(self):
        draft, sources = fixture()
        draft['body_paragraphs'].append('A future payoff is guaranteed.')
        rejected = engine.EditorialError('claim_grounding_failed', 'Grounding failed',
                                         stage='scope_review', feedback='body_paragraphs[1]: future payoff not in source')
        with patch.object(engine, 'review_scope', side_effect=[rejected, {'grounding': {}}]) as review:
            result, _ = engine.write_story({'draft_seed': draft}, {}, sources, kind='news')
        self.assertEqual(result['body_paragraphs'], [draft['body_paragraphs'][0]])
        self.assertEqual(review.call_count, 2)
        self.assertEqual(review.call_args.args[0]['editorial_headline'], draft['editorial_headline'])

    def test_news_keeps_sole_paragraph_when_reviewer_rejects_it(self):
        draft, sources = fixture()
        rejected = engine.EditorialError('claim_grounding_failed', 'Grounding failed',
                                         stage='scope_review', feedback='body_paragraphs[0]: unsupported')
        with patch.object(engine, 'review_scope', side_effect=rejected) as review:
            with self.assertRaises(engine.EditorialError):
                engine.write_story({'draft_seed': draft}, {}, sources, kind='news')

    def test_omitted_entity_gets_second_full_grounding_review(self):
        draft, sources = fixture()
        first = accepted_review(draft)
        first['entities_and_roles_preserved'] = False
        first['reason'] = 'The draft omits a separately named organization.'
        with patch.object(engine, 'call_json', side_effect=[first, accepted_review(draft)]) as model:
            result = engine.review_scope(draft, sources)
        self.assertTrue(result['grounding'])
        self.assertEqual(model.call_count, 2)
        self.assertIn('An omitted source detail alone', model.call_args.args[0])

    def test_actual_changed_entity_stays_rejected(self):
        draft, sources = fixture()
        first = accepted_review(draft)
        first['entities_and_roles_preserved'] = False
        first['reason'] = 'The draft names a different organization.'
        with patch.object(engine, 'call_json', return_value=first) as model:
            with self.assertRaises(engine.EditorialError):
                engine.review_scope(draft, sources)
        self.assertEqual(model.call_count, 1)
    def test_news_rechecks_whole_draft_without_unsupported_optional_limitation(self):
        draft, sources = fixture()
        rejected = engine.EditorialError('claim_grounding_failed', 'Grounding failed',
                                         stage='scope_review', feedback='limitation: not stated in source')
        with patch.object(engine, 'review_scope', side_effect=[rejected, {'grounding': {}}]) as review:
            result, _ = engine.write_story({'draft_seed': draft}, {}, sources, kind='news')
        self.assertEqual(result['limitation'], '')
        self.assertEqual(review.call_count, 2)
        self.assertEqual(review.call_args.args[0]['limitation'], '')

    def test_news_rechecks_whole_draft_without_unsupported_ai_reading(self):
        draft, sources = fixture()
        draft['for_ai'] = 'The source reports a new model benefit.'
        rejected = engine.EditorialError('claim_grounding_failed', 'Grounding failed',
                                         stage='scope_review', feedback='for_ai: forecast not stated in source')
        with patch.object(engine, 'review_scope', side_effect=[rejected, {'grounding': {}}]) as review:
            result, _ = engine.write_story({'draft_seed': draft}, {}, sources, kind='news')
        self.assertEqual(result['for_ai'], '')
        self.assertEqual(result['limitation'], draft['limitation'])
        self.assertEqual(review.call_count, 2)

    def test_long_news_report_is_read_in_complete_bounded_segments(self):
        source = {'source_number': 1, 'evidence_basis': 'full_source',
                  'evidence': ('A complete report paragraph with substantial context.\n' * 1700)}
        with patch.object(engine, 'read_segment', return_value=('Checked segment note',
                                                                ['A complete report paragraph'])) as reader:
            notes, trace = engine.compile_evidence([source])
        self.assertGreater(len(trace), 24)
        self.assertLessEqual(len(trace), 40)
        self.assertEqual(trace[0]['start'], 0)
        self.assertEqual(trace[-1]['end'], len(source['evidence']))
        self.assertEqual(reader.call_count, len(notes))

    def test_news_copied_source_wording_is_paraphrased_then_fully_reviewed(self):
        draft, sources = fixture()
        draft['body_paragraphs'] = [sources[0]['evidence']]
        edited = {key: value for key, value in draft.items() if key != 'support'}
        edited['body_paragraphs'] = ['Researchers questioned 142 musicians about AI and recorded concerns about payment.']
        with patch.object(engine, 'call_json', return_value=edited) as model, \
             patch.object(engine, 'review_scope', return_value={'grounding': {}}) as review:
            result, _ = engine.write_story({'draft_seed': draft}, {}, sources, kind='news')
        self.assertEqual(result['body_paragraphs'], edited['body_paragraphs'])
        self.assertEqual(model.call_args.kwargs['stage'], 'reading_level')
        self.assertEqual(review.call_count, 1)

    def test_research_copied_source_wording_is_paraphrased_then_fully_reviewed(self):
        draft, sources = fixture()
        draft['body_paragraphs'] = [sources[0]['evidence']]
        edited = {key: value for key, value in draft.items() if key != 'support'}
        edited['body_paragraphs'] = ['The survey records concerns about payment from 142 musicians.']
        with patch.object(engine, 'call_json', return_value=edited) as model, \
             patch.object(engine, 'review_scope', return_value={'grounding': {}}) as review:
            result, _ = engine.write_story({'draft_seed': draft}, {}, sources, kind='abstract')
        self.assertEqual(result['body_paragraphs'], edited['body_paragraphs'])
        self.assertEqual(model.call_args.kwargs['stage'], 'reading_level')
        self.assertEqual(review.call_count, 1)

    def test_publisher_name_digits_are_valid_source_metadata(self):
        draft, sources = fixture()
        sources[0]['publisher'] = 'FOX5 Vegas'
        draft['editorial_headline'] = 'FOX5 Vegas reports musician concerns about AI payment'
        self.assertEqual(engine.validate_draft(draft, sources)['editorial_headline'],
                         draft['editorial_headline'])
        draft['editorial_headline'] = 'FOX6 Vegas reports musician concerns about AI payment'
        with self.assertRaisesRegex(engine.EditorialError, 'unsupported_number'):
            engine.validate_draft(draft, sources)

    def test_absent_dimensions_do_not_force_an_invented_effect(self):
        for field in ('for_humans', 'for_ai'):
            draft, sources = fixture()
            draft[field] = ''
            with patch.object(engine, 'call_json', side_effect=[draft, accepted_review(draft)]) as model:
                result, proof = engine.write_story({}, {}, sources)
            self.assertEqual(result[field], '')
            self.assertEqual(proof['engine_version'], engine.ENGINE_VERSION)
            self.assertEqual(model.call_count, 2)

    def test_length_limits_are_sent_to_the_model_before_validation(self):
        draft, sources = fixture()
        with patch.object(engine, 'call_json', side_effect=[draft, accepted_review()]) as model:
            engine.write_story({}, {}, sources, kind='preprint')
        schema = model.call_args_list[0].args[1]
        for field, maximum in engine.FIELD_LIMITS.items():
            self.assertEqual(schema['properties'][field]['maxLength'], maximum)
        self.assertEqual(schema['properties']['for_ai']['minLength'], 0)
        self.assertEqual(schema['properties']['claim_status']['enum'], ['study'])
        self.assertEqual(schema['properties']['support']['items']['properties']['source_number']['enum'], [1])
        draft['editorial_headline'] = 'x' * 131
        with self.assertRaises(engine.EditorialError) as caught:
            engine.validate_draft(draft, sources)
        self.assertEqual(engine.failure_diagnostic(caught.exception, 'generation')['code'], 'draft_field_too_long')
        self.assertEqual(caught.exception.field, 'editorial_headline')

    def test_retry_corrects_a_rejected_draft_without_weakening_checks(self):
        good, sources = fixture()
        bad = copy.deepcopy(good)
        bad['what_happened'] = 'Researchers asked 263 musicians about AI.'
        with patch.object(engine, 'call_json', side_effect=[bad, good, accepted_review()]) as model:
            result, _ = engine.write_story({}, {}, sources)
        self.assertEqual(result['what_happened'], good['what_happened'])
        self.assertIn('numeric value', model.call_args_list[1].args[0])
        self.assertIn('PREVIOUS REJECTED DRAFT', model.call_args_list[1].args[0])
        self.assertIn('263 musicians', model.call_args_list[1].args[0])

    def test_research_resolves_support_ids_to_verified_source_passages(self):
        draft, sources = fixture()
        quotes = engine.research_quotes(sources)
        wanted = 'A large majority raised concerns about payment.'
        draft['support'] = [{'field': field, 'source_number': 1, 'quote_id': quotes.index(wanted)}
                            for field in engine.SUPPORT_FIELDS]
        with patch.object(engine, 'call_json', side_effect=[draft, accepted_review()]):
            result, proof = engine.write_story({}, {}, sources, kind='preprint')
        self.assertEqual(proof['support'][0]['quote'], wanted)
        self.assertNotIn('quote_id', result['support'][0])

    def test_exhausted_retries_keep_the_actual_validation_reason(self):
        draft, sources = fixture()
        draft['support'][0]['quote'] = 'This quotation is absent from the source.'
        with patch.object(engine, 'call_json', return_value=draft) as model:
            with self.assertRaises(engine.EditorialError) as caught:
                engine.write_story({}, {}, sources)
        self.assertEqual(model.call_count, 3)
        self.assertEqual(caught.exception.code, 'draft_quote_unsupported')
        self.assertEqual(caught.exception.stage, 'draft_validation')

    def test_scope_review_reason_is_private_but_failed_checks_are_visible(self):
        draft, sources = fixture()
        review = {**accepted_review(), 'population_preserved': False,
                  'reason': 'PRIVATE_EVIDENCE_SENTINEL'}
        with patch.object(engine, 'call_json', return_value=review):
            with self.assertRaises(engine.EditorialError) as caught:
                engine.review_scope(draft, sources)
        diagnostic = engine.failure_diagnostic(caught.exception, 'generation')
        self.assertEqual(diagnostic['failed_checks'], ['population_preserved'])
        self.assertEqual(diagnostic['stage'], 'scope_review')
        self.assertNotIn('PRIVATE_EVIDENCE_SENTINEL', json.dumps(diagnostic))
        self.assertIn('PRIVATE_EVIDENCE_SENTINEL', caught.exception.feedback)

    def test_segment_retry_preserves_the_entire_evidence(self):
        text = ('A measured benefit was reported for the tested group. ' * 140) + ' Final correction.'
        good = {'note': 'The tested group showed a benefit.',
                'quotes': ['A measured benefit was reported']}
        calls = []
        def model(prompt, *args, **kwargs):
            calls.append(prompt)
            if len(calls) == 1:
                return {**good, 'quotes': ['An invented quote that is not in this source.']}
            return good
        with patch.object(engine, 'call_json', side_effect=model):
            compiled, trace = engine.compile_evidence([{'source_number': 1, 'evidence': text}])
        self.assertEqual(len(calls), len(trace) + 1)
        self.assertEqual(trace[0]['start'], 0)
        self.assertEqual(trace[-1]['end'], len(text))
        self.assertIn('Final correction.', calls[-1])
        for before, after in zip(trace, trace[1:]):
            self.assertLessEqual(after['start'], before['end'])
        self.assertTrue(all(row['evidence_quotes'] for row in compiled))

    def test_bad_segment_stops_with_a_reading_diagnostic(self):
        with patch.object(engine, 'call_json', return_value={'note': 'A note.', 'quotes': ['Missing quotation.']}) as model:
            with self.assertRaises(engine.EditorialError) as caught:
                engine.read_segment('The actual complete source segment.', None)
        self.assertEqual(model.call_count, 2)
        self.assertEqual(caught.exception.code, 'segment_support_invalid')
        self.assertEqual(caught.exception.stage, 'evidence_reading')

    def test_raw_database_error_is_not_a_public_diagnostic(self):
        error = RuntimeError('PRIVATE_DATABASE_ROW sb_secret_example')
        diagnostic = engine.failure_diagnostic(error, 'persistence')
        self.assertEqual(diagnostic['stage'], 'persistence')
        self.assertEqual(diagnostic['code'], 'unexpected_error')
        self.assertNotIn('PRIVATE_DATABASE_ROW', json.dumps(diagnostic))
        self.assertNotIn('sb_secret_example', json.dumps(diagnostic))

    def test_research_must_still_have_a_study_status_and_limitation(self):
        for field, value in [('limitation', ''), ('claim_status', 'reporting')]:
            draft, sources = fixture()
            draft[field] = value
            with self.assertRaises(engine.EditorialError) as caught:
                engine.validate_draft(draft, sources, 'preprint')
            self.assertEqual(caught.exception.code, 'research_status_missing')


class ModelTransport(unittest.TestCase):
    def response(self, content='{}', finish='stop'):
        response = Mock()
        response.json.return_value = {'choices': [{'finish_reason': finish, 'message': {'content': content}}]}
        return response

    def test_unfinished_invalid_and_missing_answers_have_distinct_codes(self):
        cases = [('{}', 'length', 'model_output_unfinished'),
                 ('PRIVATE_BROKEN_JSON', 'stop', 'model_json_invalid'),
                 ('', 'stop', 'model_answer_missing'),
                 ('[]', 'stop', 'model_object_missing')]
        for content, finish, code in cases:
            with self.subTest(code=code), patch.object(engine.requests, 'post', return_value=self.response(content, finish)):
                with self.assertRaises(engine.EditorialError) as caught:
                    engine.call_json('Source data', stage='scope_review')
            diagnostic = engine.failure_diagnostic(caught.exception, 'generation')
            self.assertEqual(diagnostic['code'], code)
            self.assertEqual(diagnostic['stage'], 'scope_review')
            self.assertNotIn('PRIVATE_BROKEN_JSON', json.dumps(diagnostic))

    def test_http_and_timeout_errors_do_not_leak_server_content(self):
        for error, code in [(requests.HTTPError('PRIVATE_SERVER_REPLY'), 'model_http_error'),
                            (requests.Timeout('PRIVATE_SERVER_REPLY'), 'model_timeout')]:
            with patch.object(engine.requests, 'post', side_effect=error):
                with self.assertRaises(engine.EditorialError) as caught:
                    engine.call_json('Source data', stage='draft')
            self.assertEqual(caught.exception.code, code)
            self.assertNotIn('PRIVATE_SERVER_REPLY', json.dumps(engine.failure_diagnostic(caught.exception, 'draft')))

    def test_total_runtime_expiry_stays_deferred(self):
        with patch.object(engine.time, 'monotonic', side_effect=[0, 0, 99]), \
             patch.object(engine.requests, 'post', side_effect=requests.Timeout):
            with self.assertRaises(TimeoutError):
                engine.call_json('Source data', deadline=100)


class GenerationCheckpoints(unittest.TestCase):
    def context(self, stack, folder):
        root = Path(folder)
        (root / 'data/research/private').mkdir(parents=True)
        output = io.StringIO()
        stack.enter_context(redirect_stdout(output))
        stack.enter_context(patch.dict(os.environ, {
            'SUPABASE_URL': 'https://example.invalid', 'SUPABASE_SECRET_KEY': 'test',
            'GITHUB_STEP_SUMMARY': str(root / 'summary.md'),
        }, clear=True))
        stack.enter_context(patch.object(sys, 'argv', ['generate']))
        return root, output

    def news_context(self, stack, root, size):
        stack.enter_context(patch.object(news, 'ROOT', root))
        stack.enter_context(patch.object(news, 'create_client', return_value=Mock()))
        stack.enter_context(patch.object(news, 'inputs', return_value=({'release_id': '2026-W35', 'evidence': []}, {})))
        stack.enter_context(patch.object(news, 'validate_pair'))
        stack.enter_context(patch.object(news, 'current_maps'))
        draft, sources = fixture()
        items = [{'eid': f'event-{n}', 'fp': f'input-{n}', 'reuse': False,
                  'event': {}, 'relation': {'axes': {}}, 'sources': sources} for n in range(size)]
        stack.enter_context(patch.object(news, 'candidates', return_value=(items, {}, {})))
        return draft

    def test_news_saves_good_work_and_keeps_failures_separate_from_deferrals(self):
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            root, output = self.context(stack, folder)
            draft = self.news_context(stack, root, 4)
            stack.enter_context(patch.object(news, 'write_story', side_effect=[
                (draft, {}), engine.EditorialError('draft_quote_unsupported', 'PRIVATE_FEEDBACK', stage='draft_validation'), TimeoutError()]))
            save = stack.enter_context(patch.object(news, 'persist'))
            self.assertEqual(news.main(), 0)
            self.assertEqual(save.call_count, 1)
            status_text = (root / 'data/editorial/status.json').read_text()
            status = json.loads(status_text)
            self.assertEqual(status['counts'], {'selected': 4, 'generated': 1, 'rebound': 0, 'failed': 1, 'deferred': 2})
            self.assertEqual(status['failure_counts'], {'draft_quote_unsupported': 1})
            self.assertEqual(status['release_id'], '2026-W35')
            self.assertNotIn('PRIVATE_FEEDBACK', status_text + output.getvalue())

    def test_capped_news_run_keeps_retry_state_for_unselected_items(self):
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            root,_=self.context(stack,folder)
            draft=self.news_context(stack,root,2)
            stack.enter_context(patch.object(sys,'argv',['generate','--limit','1']))
            items=news.candidates.return_value[0]
            news.candidates.return_value=(items,{}, {'input-1':{'attempts':2}})
            stack.enter_context(patch.object(news,'write_story',return_value=(draft,{})))
            stack.enter_context(patch.object(news,'persist'))
            self.assertEqual(news.main(),0)
            state=json.loads((root/'data/editorial/retry-state.json').read_text())
            self.assertEqual(state['input-1']['attempts'],2)

    def test_database_failure_remains_failed_with_its_stage_visible(self):
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            root, output = self.context(stack, folder)
            draft = self.news_context(stack, root, 1)
            stack.enter_context(patch.object(news, 'write_story', return_value=(draft, {})))
            stack.enter_context(patch.object(news, 'persist', side_effect=RuntimeError('PRIVATE_DATABASE_ROW')))
            self.assertEqual(news.main(), 1)
            status = json.loads((root / 'data/editorial/status.json').read_text())
            self.assertEqual(status['failed_items'][0]['stage'], 'persistence')
            self.assertNotIn('PRIVATE_DATABASE_ROW', json.dumps(status) + output.getvalue())

    def research_context(self, stack, root, size):
        stack.enter_context(patch.object(research, 'ROOT', root))
        stack.enter_context(patch('supabase.create_client', return_value=Mock()))
        draft, sources = fixture()
        papers = [{'key': f'paper:{n}', 'original_headline': 'Musician study',
                   'url': f'https://example.org/paper/{n}', 'date': '2026-09-07',
                   'publisher': 'Study archive', 'source': 'arxiv', 'metadata_sha256': f'hash-{n}',
                   'abstract': sources[0]['evidence']} for n in range(size)]
        stack.enter_context(patch.object(research, 'load', return_value=(
            {'period_start': '2026-09-01', 'period_end': '2026-09-07', 'papers': papers}, {})))
        return draft

    def test_research_checkpoints_preserve_good_summaries_and_original_links(self):
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            root, output = self.context(stack, folder)
            draft = self.research_context(stack, root, 3)
            stack.enter_context(patch.object(research, 'write_story', side_effect=[
                (draft, {}), engine.EditorialError('model_json_invalid', 'PRIVATE_FEEDBACK', stage='draft'), TimeoutError()]))
            research.main()
            status_text = (root / 'data/research/generation-status.json').read_text()
            status = json.loads(status_text)
            self.assertEqual([status[k] for k in ['generated', 'failed', 'deferred']], [1, 1, 1])
            self.assertEqual(status['failure_counts'], {'model_json_invalid': 1})
            papers = json.loads((root / 'data/research/public.json').read_text())['papers']
            self.assertEqual(sum(p['has_editorial'] for p in papers), 1)
            self.assertEqual(len(papers), 3)
            self.assertTrue(all(p['url'] for p in papers))
            self.assertNotIn('PRIVATE_FEEDBACK', status_text + output.getvalue())
            self.assertIn('model_json_invalid', (root / 'summary.md').read_text())

    def test_failed_refresh_keeps_valid_summary_for_unchanged_evidence(self):
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            root, _ = self.context(stack, folder)
            self.research_context(stack, root, 1)
            data, _ = research.load()
            prior = {**data['papers'][0], 'has_editorial': True,
                     'headline': 'Previously checked summary', 'prompt_version': 'older'}
            prior.pop('abstract')
            research.load.return_value = (data, {prior['key']: prior})
            stack.enter_context(patch.object(research, 'write_story', side_effect=TimeoutError()))
            research.main()
            saved = json.loads((root / 'data/research/public.json').read_text())['papers'][0]
            self.assertTrue(saved['has_editorial'])
            self.assertEqual(saved['headline'], prior['headline'])
            self.assertNotIn('abstract', saved)

    def test_full_paper_reaches_writer_but_private_text_never_reaches_public_json(self):
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            root, _ = self.context(stack, folder)
            draft = self.research_context(stack, root, 1)
            data,_=research.load()
            data['papers'][0].pop('abstract')
            data['papers'][0]['pdf_url']='https://arxiv.org/pdf/2609.35767v1'
            stack.enter_context(patch.object(research, 'read_paper', return_value={
                'status':'read','text':'PRIVATE COMPLETE PAPER with final-page limitations',
                'pages':12,'text_sha256':'paper-hash','pdf_sha256':'pdf-hash',
                'url':'https://arxiv.org/pdf/2609.35767v1'}))
            writer=stack.enter_context(patch.object(research, 'write_story', return_value=(draft,{})))
            research.main()
            self.assertEqual(writer.call_args.kwargs['kind'],'paper')
            self.assertIn('final-page limitations',writer.call_args.args[2][0]['evidence'])
            public=(root/'data/research/public.json').read_text()
            saved=json.loads(public)['papers'][0]
            self.assertEqual(saved['summary_basis'],'Summary of the paper')
            self.assertEqual(saved['paper_pages'],12)
            self.assertNotIn('PRIVATE COMPLETE PAPER',public)

    def test_unavailable_pdf_does_not_downgrade_an_existing_paper_reading(self):
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            root, _ = self.context(stack, folder)
            self.research_context(stack, root, 1)
            data, _ = research.load()
            prior={**data['papers'][0],'has_editorial':True,'evidence_scope':'paper_text',
                   'headline':'Checked full-paper summary','prompt_version':'older'}
            prior.pop('abstract')
            research.load.return_value=(data,{prior['key']:prior})
            stack.enter_context(patch.object(research,'read_paper',return_value={'status':'pdf_unavailable'}))
            writer=stack.enter_context(patch.object(research,'write_story'))
            research.main()
            writer.assert_not_called()
            saved=json.loads((root/'data/research/public.json').read_text())['papers'][0]
            self.assertEqual(saved['evidence_scope'],'paper_text')
            self.assertEqual(saved['headline'],prior['headline'])

    def test_research_with_no_valid_drafts_still_reports_failure(self):
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            root, _ = self.context(stack, folder)
            self.research_context(stack, root, 1)
            stack.enter_context(patch.object(research, 'write_story', side_effect=engine.EditorialError(
                'model_json_invalid', 'Invalid JSON', stage='draft')))
            with self.assertRaises(SystemExit) as caught:
                research.main()
            self.assertEqual(caught.exception.code, 1)
            self.assertTrue((root / 'data/research/generation-status.json').exists())

    def test_repeated_model_exhaustion_stops_after_three_and_saves_remaining_queue(self):
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            root, output = self.context(stack, folder)
            self.research_context(stack, root, 8)
            error=research.ai_runtime.AIError('No public answer',code='model_output_limit',reasoning_tokens=32768)
            error.stage='scope_review'
            writer=stack.enter_context(patch.object(research,'write_story',side_effect=error))
            with self.assertRaises(SystemExit):research.main()
            self.assertEqual(writer.call_count,3)
            status=json.loads((root/'data/research/generation-status.json').read_text())
            self.assertEqual((status['failed'],status['deferred']),(3,5))
            self.assertEqual(status['failure_counts'],{'model_output_limit':3})
            self.assertEqual(status['failed_items'][0]['stage'],'scope_review')
            self.assertEqual(len(json.loads((root/'data/research/public.json').read_text())['papers']),8)

    def test_account_failure_defers_the_rest_without_more_model_calls(self):
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            root, _ = self.context(stack, folder)
            self.research_context(stack, root, 4)
            writer=stack.enter_context(patch.object(research,'write_story',side_effect=research.ai_runtime.AIError(
                'Access unavailable',code='model_access_or_quota',fatal=True)))
            with self.assertRaises(SystemExit):research.main()
            self.assertEqual(writer.call_count,1)
            status=json.loads((root/'data/research/generation-status.json').read_text())
            self.assertEqual((status['failed'],status['deferred']),(1,3))


if __name__ == '__main__':
    unittest.main()
