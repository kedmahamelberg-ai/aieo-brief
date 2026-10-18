"""Source binding, strict rejection and private retry feedback for news."""
import copy
import json
import unittest
from unittest.mock import patch
from test_editorial_recovery import engine, fixture, accepted_review


class NewsSourceSupport(unittest.TestCase):
    def test_numeric_tokens_do_not_depend_on_source_language_boundaries(self):
        text = '模型Example5.0-9B在9项中通过8项，自2021年迭代4次，类别10B。'
        self.assertEqual(engine.numeric_values(text), {'5.0', '9', '8', '2021', '4', '10'})
        self.assertNotIn('0', engine.numeric_values(text))
        self.assertEqual(engine.numeric_values('Reported 12.5% of 1,000 cases.'), {'12.5%', '1,000'})

    def test_supported_cjk_numbers_pass_but_invented_values_still_fail(self):
        draft, sources = fixture()
        sources[0]['evidence'] += ' 模型Example5.0-9B在9项中通过8项，自2021年迭代4次，类别10B。'
        draft['what_happened'] = 'The report says Example5.0-9B led 8 of 9 tests after 4 updates since 2021.'
        self.assertEqual(engine.validate_draft(draft, sources)['what_happened'], draft['what_happened'])
        for text in ('The model led 80 of 90 tests.', 'The model has 11B parameters.',
                     'The report dates to 2022.', 'The model is Example5.1-9B.'):
            bad = copy.deepcopy(draft)
            bad['what_happened'] = text
            with self.subTest(text=text), self.assertRaises(engine.EditorialError) as caught:
                engine.validate_draft(bad, sources)
            self.assertEqual(caught.exception.code, 'unsupported_number')

    def test_decimal_fragments_and_percentage_changes_cannot_pass(self):
        draft, sources = fixture()
        sources[0]['evidence'] += ' Model5.0 achieved 12.5% in a separate test.'
        for text in ('The result was 0.', 'The result was 5.', 'The result was 12.5.',
                     'The result was 12%.', 'The result was 125%.'):
            bad = copy.deepcopy(draft)
            bad['what_happened'] = text
            with self.subTest(text=text), self.assertRaises(engine.EditorialError) as caught:
                engine.validate_draft(bad, sources)
            self.assertEqual(caught.exception.code, 'unsupported_number')

    def test_news_uses_source_bound_ids_and_validates_original_text(self):
        draft, sources = fixture()
        catalog = engine.support_catalog(sources)
        index = next(i for i, row in enumerate(catalog) if row['quote'] == draft['support'][0]['quote'])
        draft['support'] = [{'field': field, 'quote_id': index} for field in engine.SUPPORT_FIELDS]
        with patch.object(engine, 'call_json', side_effect=[draft, accepted_review()]) as model:
            result, proof = engine.write_story({}, {}, sources)
        schema = model.call_args_list[0].args[1]
        self.assertNotIn('source_number', schema['properties']['support']['items']['properties'])
        self.assertNotIn('quote', schema['properties']['support']['items']['properties'])
        self.assertEqual(proof['support'][0]['source_number'], 1)
        self.assertIn(result['support'][0]['quote'], sources[0]['evidence'])
        self.assertEqual(model.call_args_list[-1].kwargs['stage'], 'scope_review')

    def test_invalid_ids_and_wrong_source_still_fail(self):
        draft, sources = fixture()
        catalog = engine.support_catalog(sources)
        for index in (-1, len(catalog), True, '0'):
            bad = copy.deepcopy(draft)
            bad['support'][0] = {'field': 'editorial_headline', 'quote_id': index}
            with self.subTest(index=index), self.assertRaises(ValueError):
                engine.resolve_support(bad, catalog)
        bad = copy.deepcopy(draft)
        bad['support'][0] = {'field': 'editorial_headline', 'quote_id': 0, 'source_number': 2}
        with self.assertRaises(ValueError):
            engine.resolve_support(bad, catalog)

    def test_same_passage_in_two_sources_retains_both_bindings(self):
        _, sources = fixture()
        sources.append({**sources[0], 'source_number': 2})
        catalog = engine.support_catalog(sources)
        quote = catalog[0]['quote']
        self.assertEqual({row['source_number'] for row in catalog if row['quote'] == quote}, {1, 2})

    def test_earlier_segment_quote_survives_repeated_source_number(self):
        draft, sources = fixture()
        sources.append({'source_number': 1, 'evidence': 'The final segment contains a separate limitation.'})
        self.assertEqual(engine.validate_draft(draft, sources)['support'], draft['support'])
        catalog = engine.support_catalog(sources)
        self.assertIn(draft['support'][0]['quote'], [row['quote'] for row in catalog])

    def test_quote_cannot_cross_segment_boundary_or_match_another_source(self):
        draft, sources = fixture()
        sources.extend([{'source_number': 2, 'evidence': 'An unrelated report describes a different result.'},
                        {'source_number': 1, 'evidence': 'The final segment contains a separate limitation.'}])
        for quote in ('An unrelated report describes a different result.',
                      'The survey cannot represent every musician. The final segment'):
            bad = copy.deepcopy(draft)
            bad['support'][0]['quote'] = quote
            with self.assertRaises(engine.EditorialError) as caught:
                engine.validate_draft(bad, sources)
            self.assertEqual(caught.exception.code, 'draft_quote_unsupported')

    def test_real_quote_cannot_bypass_meaning_review(self):
        draft, sources = fixture()
        draft['editorial_headline'] = 'AI guarantees fair payment for every musician'
        review = {**accepted_review(), 'headline_supported': False, 'reason': 'The source gives no guarantee.'}
        with patch.object(engine, 'call_json', side_effect=[copy.deepcopy(draft), review] * 3):
            with self.assertRaises(engine.EditorialError) as caught:
                engine.write_story({}, {}, sources)
        self.assertEqual(caught.exception.code, 'source_scope_review_failed')

    def test_numeric_feedback_names_fields_without_public_leak(self):
        good, sources = fixture()
        bad = copy.deepcopy(good)
        bad['what_happened'] = 'Researchers asked 263 musicians about AI.'
        bad['body_paragraphs'] = ['The report described 999 responses.']
        with self.assertRaises(engine.EditorialError) as caught:
            engine.validate_draft(bad, sources)
        error = caught.exception
        self.assertEqual(error.code, 'unsupported_number')
        for value in ('what_happened', 'body_paragraphs[0]', '263', '999'):
            self.assertIn(value, error.feedback)
        diagnostic = json.dumps(engine.failure_diagnostic(error, 'generation'))
        self.assertNotIn('263', diagnostic)
        self.assertNotIn('999', diagnostic)
        with patch.object(engine, 'call_json', side_effect=[bad, good, accepted_review()]) as model:
            result, _ = engine.write_story({}, {}, sources)
        self.assertIn('263', model.call_args_list[1].args[0])
        self.assertEqual(result['what_happened'], good['what_happened'])


if __name__ == '__main__':
    unittest.main()
