import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch, Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import government_briefs as gov


def source(**changes):
    return {'id': 'test-ai-item', 'country': 'Estonia', 'country_code': 'EE',
            'url': 'https://valitsus.ee/news/ai', 'published_at': '2026-11-11T23:00:00Z',
            'published_date': '2026-11-12', 'classification_status': 'provisional',
            'translation_complete': True, 'relevance': 'not_related', 'topics': [],
            'english_summary': 'Estonia plans to discuss rules for AI use in healthcare.', **changes}


def draft(item, deadline=None):
    return {'include': True, 'headline': 'Estonia plans talks on AI rules for healthcare',
            'summary': 'Estonia says it plans to discuss rules for AI use in healthcare.',
            'support_quote': item['english_summary']}


def snapshot(*items):
    return {'as_of': '2026-11-13T14:00:00Z', 'items': list(items)}


class GovernmentBriefsTests(unittest.TestCase):
    def test_security_relevance_is_not_ai_relevance(self):
        self.assertTrue(gov.candidate(source()))
        self.assertFalse(gov.candidate(source(english_summary='Estonia announces new border checks.',
                                              relevance='related', topics=['artificial_intelligence'])))

    def test_unfinished_and_unsafe_sources_are_excluded(self):
        for changes in ({'translation_complete': False}, {'classification_status': 'needs_review'},
                        {'url': 'javascript:alert(1)'}, {'published_date': 'unknown'}, {'country_code': ''}):
            with self.subTest(changes=changes):
                self.assertFalse(gov.candidate(source(**changes)))

    def test_original_local_publication_day_is_preserved(self):
        self.assertEqual(gov.published_day(source()), '2026-11-12')

    def test_passing_mention_can_be_rejected_after_content_check(self):
        state = gov.refresh(snapshot(source()), {}, writer=lambda *a: {'include': False})
        self.assertFalse(state['records'])
        self.assertEqual(len(state['checked']), 1)

    def test_unchanged_items_are_not_rewritten_and_duplicates_are_merged(self):
        writer = Mock(side_effect=draft)
        state = gov.refresh(snapshot(source(), source()), {}, writer=writer)
        self.assertEqual(writer.call_count, 1)
        gov.refresh(snapshot(source()), state, writer=writer)
        self.assertEqual(writer.call_count, 1)

    def test_changed_evidence_is_withdrawn_if_recheck_fails(self):
        state = gov.refresh(snapshot(source()), {}, writer=draft)
        changed = source(english_summary='Estonia cancels its proposed AI healthcare discussion.')
        result = gov.refresh(snapshot(changed), state, writer=Mock(side_effect=ValueError('unsupported')))
        self.assertFalse(result['records'])
        self.assertEqual(len(result['failures']), 1)
        self.assertNotEqual(result['checked']['test-ai-item'], gov.fingerprint(changed))

    def test_now_non_ai_source_removes_previous_summary(self):
        state = gov.refresh(snapshot(source()), {}, writer=draft)
        result = gov.refresh(snapshot(source(english_summary='Estonia discusses water quality.')), state, writer=draft)
        self.assertFalse(result['records'])

    def test_failures_do_not_starve_new_or_older_unattempted_items(self):
        state = gov.refresh(snapshot(source()), {}, writer=Mock(side_effect=TimeoutError), limit=1)
        result = gov.refresh(snapshot(source(), source(id='older', published_date='2026-11-01')), state, writer=draft, limit=1)
        self.assertIn('older', result['records'])

    def test_incomplete_monitor_response_preserves_checkpoint(self):
        with self.assertRaises(ValueError):
            gov.refresh({'items': []}, {}, writer=draft)

    def test_short_output_and_exact_support_are_required(self):
        for changes in ({'summary': 'AI ' * 46}, {'headline': 'AI ' * 17},
                        {'support_quote': 'This passage does not occur in the source.'},
                        {'summary': 'A statement. Another. A third. AI fourth.'}, {'details': ['AI ' * 91]}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                gov.validate_draft({**draft(source()), **changes}, source())

    def test_original_source_is_required_and_related_links_are_not_evidence(self):
        response = Mock(content=b'<html><main><nav>Artificial intelligence news</nav><p>' +
                        b'This official announcement discusses drinking water and public health. ' * 5 +
                        b'</p></main></html>', headers={'Content-Type': 'text/html'})
        response.raise_for_status.return_value = None
        with patch.object(gov.requests, 'get', return_value=response):
            body = gov.official_text(source()['url'])
        self.assertNotIn('Artificial intelligence', body)
        self.assertIn('drinking water', body)

    def test_independent_original_source_review_can_withhold_draft(self):
        output = draft(source())
        failed = dict.fromkeys(('substantive_ai','main_announcement_matches','all_claims_supported',
                               'attribution_preserved','simple_english'), True)
        failed['substantive_ai'] = False
        with patch.object(gov, 'official_text', return_value='No substantive AI statement here.'), \
             patch('editorial_engine.call_json', side_effect=[output, failed]), self.assertRaises(ValueError):
            gov.write_draft(source(), None)

    def test_engagement_identities_and_licensed_photos(self):
        root = Path(__file__).resolve().parents[1]
        row = gov.refresh(snapshot(source()), {}, writer=draft)
        with patch.object(gov, 'load', return_value=row):
            a = gov.cards(root)[0]
            b = gov.cards(root)[0]
        self.assertEqual(a['key'], b['key'])
        self.assertRegex(a['key'], r'^event:[a-f0-9-]{36}$')
        self.assertEqual(a['kind'], 'news')
        self.assertEqual(a['section'], 'governments')
        self.assertEqual(a['markets'], [])


if __name__ == '__main__':
    unittest.main()
