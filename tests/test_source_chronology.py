"""A dated publisher URL must not become a fresh Brief story years later."""
import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from build_site import cards
from generate_editorial_stories import candidates
from source_chronology import dated_source_year, older_source_year, public_event_ids, public_directional_counts


class SourceChronologyTests(unittest.TestCase):
    def test_old_publisher_path_is_not_presented_as_current_news(self):
        event = {'event_id': 'e709b8c6-8cbb-4316-90e6-126ccb92066f',
                 'event_date': '2026-10-31',
                 'sources': [{'url': 'https://www.nttdata.com/en-be/news/2023/the-artificial-intelligence-paradox'}]}
        self.assertEqual(older_source_year(event), 2023)
        release = {'release_id': '2026-W44', 'evidence': [event]}
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(cards(release, {'evidence': []}, {}, {}, {}), [])
        self.assertIn('source URL dates it to 2023', output.getvalue())
        selected, counts, _ = candidates(release, {'evidence': []}, ({}, {}, {}, {}))
        self.assertEqual(selected, [])
        self.assertEqual(counts['source_date_mismatch'], 1)
        self.assertEqual(public_event_ids(release), set())
        relationship = {'evidence': [{'event_id': event['event_id'], 'axes': {
            'human': {'direction': 'mixed'}, 'ai': {'direction': 'gain'}}}]}
        self.assertEqual(sum(public_directional_counts(release, relationship)['human'].values()), 0)

    def test_url_year_needs_a_clear_publication_path_and_all_sources(self):
        self.assertEqual(dated_source_year('https://example.org/news/2026/story'), 2026)
        self.assertIsNone(dated_source_year('https://example.org/story/about-2023'))
        event = {'event_date': '2026-10-31', 'sources': [
            {'url': 'https://example.org/news/2023/story'},
            {'url': 'https://example.org/story-without-date'}]}
        self.assertIsNone(older_source_year(event))
        event['sources'][1]['url'] = 'https://example.org/news/2026/new-report'
        self.assertIsNone(older_source_year(event))
