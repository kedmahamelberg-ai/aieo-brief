import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from government_briefs import fingerprint, monitor_record
from verify_live_government_coverage import verify


class LiveGovernmentCoverageTests(unittest.TestCase):
    def setUp(self):
        self.item = {'id': 'lu-item', 'country': 'Luxembourg', 'country_code': 'LU',
                     'url': 'https://example.lu/ai', 'published_date': '2026-11-22',
                     'translation_complete': True, 'classification_status': 'provisional',
                     'topics': ['artificial_intelligence'],
                     'english_summary': 'Luxembourg launched an AI-supported marketplace.',
                     'ticker_message': 'Luxembourg launches an AI marketplace.'}
        self.snapshot = {'as_of': '2026-11-23T08:00:00Z', 'items': [self.item]}
        sha = fingerprint(self.item)
        self.record = monitor_record(self.item, sha)
        self.state = {'policy': 'government-ai-brief-v4',
                      'records': {'lu-item': self.record}, 'checked': {'lu-item': sha}}
        self.public_item = {**self.record, 'deck': self.record['summary'], 'key': 'government-card-key'}
        self.public = {'government_count': 1, 'governments': [self.public_item]}
        self.html = '<article class="feed-story government-card" data-key="government-card-key" data-date="2026-11-22"></article>'

    def test_exact_monitor_saved_public_and_card_ids_pass(self):
        result = verify(self.snapshot, self.state, self.public, self.html)
        self.assertEqual((result['monitor_eligible'], result['brief_saved'], result['brief_live_data'],
                          result['brief_live_cards']), (1, 1, 1, 1))

    def test_missing_saved_import_fails_before_publication(self):
        self.state['records'].clear()
        with self.assertRaisesRegex(ValueError, 'lu-item'):
            verify(self.snapshot, self.state, self.public, self.html)

    def test_stale_live_copy_and_missing_card_fail(self):
        self.public_item['deck'] = 'Outdated claim'
        with self.assertRaisesRegex(ValueError, 'stale deck'):
            verify(self.snapshot, self.state, self.public, self.html)
        self.public_item['deck'] = self.record['summary']
        with self.assertRaisesRegex(ValueError, 'Live Governments say cards'):
            verify(self.snapshot, self.state, self.public, '')

    def test_duplicate_live_card_fails(self):
        with self.assertRaisesRegex(ValueError, 'duplicates'):
            verify(self.snapshot, self.state, self.public, self.html + self.html)


if __name__ == '__main__':
    unittest.main()
