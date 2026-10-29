"""Regression tests for fail-closed publication, not claims about model accuracy."""
import copy
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import claim_grounding as grounding
import editorial_engine as engine
import editorial_corrections as corrections
from test_editorial_recovery import fixture, accepted_review


class GroundingGate(unittest.TestCase):
    def test_missing_body_or_limitation_review_cannot_publish(self):
        draft, sources = fixture()
        for field in ('body_paragraphs[0]', 'limitation', 'editorial_deck'):
            review = accepted_review()
            review['field_reviews'] = [r for r in review['field_reviews'] if r['field'] != field]
            with self.subTest(field=field), self.assertRaises(ValueError):
                grounding.validate(review, draft, sources)

    def test_uncertain_and_unsupported_claims_fail_even_with_real_quotes(self):
        draft, sources = fixture()
        for verdict in ('uncertain', 'unsupported', True, None):
            review = accepted_review()
            review['field_reviews'][0]['verdict'] = verdict
            with self.subTest(verdict=verdict), self.assertRaises(ValueError):
                grounding.validate(review, draft, sources)

    def test_every_risk_check_is_required(self):
        draft, sources = fixture()
        for check in grounding.CHECKS:
            review = accepted_review(); review[check] = False
            with self.subTest(check=check), self.assertRaises(ValueError):
                grounding.validate(review, draft, sources)

    def test_quotes_cannot_be_invented_translated_or_reassigned(self):
        draft, sources = fixture()
        for citation in ({'source_number': 1, 'quote': 'Des chercheurs ont interrogé des musiciens.'},
                         {'source_number': 2, 'quote': sources[0]['evidence'][:42]},
                         {'source_number': True, 'quote': sources[0]['evidence'][:42]}):
            review = accepted_review(); review['field_reviews'][0]['citations'] = [citation]
            with self.subTest(citation=citation), self.assertRaises(ValueError):
                grounding.validate(review, draft, sources)

    def test_catalog_preserves_every_character_and_resolves_exact_source_identity(self):
        text=('Original Français 中文 evidence with a denominator.\n'*70)+'Final limitation.'
        sources=[{'source_number':7,'evidence':text}]
        catalog=grounding.source_catalog(sources)
        self.assertEqual(''.join(row['quote'] for row in catalog),text)
        self.assertTrue(all(len(row['quote'])<=600 for row in catalog))
        index=len(catalog)-1
        result={'field_reviews':[{'citations':[{'quote_id':index}]}]}
        resolved=grounding.resolve_citations(result,catalog)['field_reviews'][0]['citations'][0]
        self.assertEqual(resolved,{'source_number':7,'quote':catalog[index]['quote']})
        self.assertIn('Final limitation.',resolved['quote'])
        self.assertIn('quote_id',result['field_reviews'][0]['citations'][0])
        for bad in (-1,len(catalog),True,'0'):
            with self.assertRaises(ValueError):grounding.resolve_citations({'field_reviews':[{'citations':[{'quote_id':bad}]}]},catalog)

    def test_catalog_review_still_requires_support_for_every_field(self):
        draft,sources=fixture();catalog=grounding.source_catalog(sources)
        review=accepted_review()
        for row in review['field_reviews']:row['citations']=[{'quote_id':0}]
        with patch.object(engine,'call_json',return_value=review) as model:
            proof=engine.review_scope(draft,sources)
        citation_schema=model.call_args.args[1]['properties']['field_reviews']['items']['properties']['citations']['items']
        self.assertEqual(citation_schema['required'],['quote_id'])
        self.assertEqual(proof['grounding']['field_reviews'][0]['citations'][0]['quote'],sources[0]['evidence'])
        review['field_reviews'][0]['verdict']='unsupported'
        with patch.object(engine,'call_json',return_value=review),self.assertRaises(engine.EditorialError):engine.review_scope(draft,sources)

    def test_duplicate_fields_cannot_hide_unreviewed_paragraph(self):
        draft, sources = fixture(); review = accepted_review()
        review['field_reviews'][-1] = copy.deepcopy(review['field_reviews'][0])
        with self.assertRaises(ValueError):grounding.validate(review, draft, sources)

    def test_valid_review_binds_private_proof_to_final_public_text(self):
        draft, sources = fixture(); review = accepted_review()
        proof = grounding.validate(review, draft, sources)
        changed = copy.deepcopy(draft); changed['editorial_deck'] += ' Changed.'
        self.assertNotEqual(proof['public_sha256'], grounding.validate(review, changed, sources)['public_sha256'])
        self.assertEqual(set(grounding.units(draft)), {r['field'] for r in proof['field_reviews']})

    def test_verifier_sees_original_not_lossy_segment_notes(self):
        draft, sources = fixture()
        notes = [{**sources[0], 'evidence': 'Lossy writer notes omit the denominator.'}]
        with patch.object(engine, 'compile_evidence', return_value=(notes, [])), patch.object(engine, 'call_json', side_effect=[draft, accepted_review()]) as model:
            engine.write_story({}, {}, sources)
        review_prompt = model.call_args.args[0]
        self.assertIn(sources[0]['evidence'], review_prompt)
        self.assertNotIn('Lossy writer notes', review_prompt)

    def test_private_rejection_details_do_not_leak_into_status(self):
        error = engine.EditorialError('claim_grounding_failed', 'Rejected', feedback='PRIVATE SOURCE PASSAGE')
        self.assertNotIn('PRIVATE SOURCE PASSAGE', json.dumps(engine.failure_diagnostic(error, 'generation')))

    def test_internal_limitation_tokens_are_never_public_prose(self):
        draft, sources = fixture()
        for value in ('limitation_source_only', 'limitation_no_outcomes_measured', 'for_humans_unstated'):
            draft['limitation'] = value
            with self.subTest(value=value), self.assertRaises(engine.EditorialError) as caught:
                engine.validate_draft(draft, sources)
            self.assertEqual(caught.exception.code, 'draft_placeholder')

    def test_review_requests_more_reasoning_without_unsupported_temperature(self):
        payload = {'choices': [{'message': {'content': '{}'}}]}
        with patch.object(engine.ai_runtime, 'uses_openai', return_value=True), patch.object(engine.ai_runtime, 'completion', return_value=payload) as request:
            engine.call_json('Original evidence', stage='scope_review')
        self.assertEqual(request.call_args.kwargs['reasoning_effort'], 'medium')
        self.assertNotIn('temperature', request.call_args.kwargs)

    def test_approved_overlays_are_idempotent_and_pending_unchanged(self):
        manifest = json.loads((corrections.ROOT / corrections.MANIFEST).read_text())
        approved = corrections.corrections()
        rows = [{'key': k, 'headline': 'pending original'} for k in manifest['pending_keys']]
        before = copy.deepcopy(rows)
        corrections.apply_corrections(rows)
        self.assertEqual(before, rows)
        for key in manifest['pending_keys']:self.assertTrue(corrections.is_locked(key))
        key = next(iter(approved)); row = {'key': key, 'unlisted_field': 'preserve'}
        corrections.apply_corrections([row]); first = copy.deepcopy(row)
        corrections.apply_corrections([row]); self.assertEqual(first, row)
        self.assertEqual(row['unlisted_field'], 'preserve')
        self.assertTrue(corrections.is_locked(key))

class WeeklyApprovedCorrections(unittest.TestCase):
    def test_repeated_research_errors_are_corrected_and_source_bound(self):
        from build_site import papers
        from editorial_corrections import apply_corrections
        from weekly_editorials import ready_valid, validate_section, validate_citation_alignment
        root = Path(__file__).resolve().parents[1]
        audit = json.loads((root/'data/editorial/weekly-corrections-2026-10-26.json').read_text())
        approved = json.loads((root/'data/weekly-overviews/approved/2026-W43.json').read_text())
        section = approved['research']
        available = {x['key']:x for x in apply_corrections(papers(), root)}
        self.assertEqual(section, audit['after'])
        self.assertTrue(ready_valid(section, available))
        validate_section(section)
        validate_citation_alignment(section['prose'], [available[k] for k in section['source_hashes']])
        self.assertNotIn('results do not always hold on new images', section['summary'])
        self.assertNotIn('gains were modest', section['summary'])
        changed = copy.deepcopy(available)
        changed[next(iter(section['source_hashes']))]['deck'] += ' Changed evidence.'
        self.assertFalse(ready_valid(section, changed))
