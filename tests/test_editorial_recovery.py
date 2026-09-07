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


def accepted_review():
    return {**dict.fromkeys(engine.REVIEW_CHECKS, True), 'reason': 'Supported.'}


class EditorialRecovery(unittest.TestCase):
    def test_absent_dimensions_do_not_force_an_invented_effect(self):
        for field in ('for_humans', 'for_ai'):
            draft, sources = fixture()
            draft[field] = ''
            with patch.object(engine, 'call_json', side_effect=[draft, accepted_review()]) as model:
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


if __name__ == '__main__':
    unittest.main()
