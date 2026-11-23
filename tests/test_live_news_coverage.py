import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from brief_contract import relationship_fingerprint
from validate_public_site import validate_home_news_coverage
from verify_live_news_coverage import verify


class LiveNewsCoverage(unittest.TestCase):
    def setUp(self):
        self.release = {'release_id': '2026-W47', 'period_start': '2026-11-16',
                        'period_end': '2026-11-22', 'content_sha256': 'source-hash',
                        'evidence': [{'event_id': 'one', 'event_date': '2026-11-21',
                                      'sources': [{'url': 'https://publisher.example/story'}]}]}
        self.relationship = {'evidence': [{'event_id': 'one'}]}
        self.brief = {'release_id': '2026-W47', 'period_start': '2026-11-16',
                      'period_end': '2026-11-22', 'source_release_sha256': 'source-hash',
                      'source_relationship_sha256': relationship_fingerprint(self.relationship),
                      'story_count': 1, 'stories': [{'event_id': 'one', 'key': 'event:one',
                                                     'has_editorial': False,
                                                     'sources': [{'url': 'https://publisher.example/story'}]}],
                      'complete_content': {'eligible_event_ids': ['one']}}
        self.homepage = ('<div id="story-feed"><article class="feed-story" data-story-card '
                         'data-kind="news" data-key="event:one" data-editorial-status="source-only">'
                         '<h2><a href="https://publisher.example/story">Report</a></h2>'
                         '</article></div>')

    def test_source_only_report_remains_visible_and_counted(self):
        with patch('verify_live_news_coverage.validate_complete_export',
                   return_value=(self.release, self.relationship)):
            result = verify({}, self.brief, self.homepage)
        self.assertEqual((result['observatory_developments'], result['brief_records'],
                          result['rendered_news_cards'], result['full_brief_articles']), (1, 1, 1, 0))

    def test_two_cards_for_many_records_fails_publication_gate(self):
        larger = {**self.brief, 'story_count': 2,
                  'stories': [{'event_id': 'one'}, {'event_id': 'two'}],
                  'complete_content': {'eligible_event_ids': ['one', 'two']}}
        with self.assertRaisesRegex(ValueError, 'Homepage has 1 news cards for 2 Brief records'):
            validate_home_news_coverage(larger, self.homepage)

    def test_duplicate_card_and_wrong_source_release_fail(self):
        with self.assertRaisesRegex(ValueError, 'Homepage has 2 news cards'):
            validate_home_news_coverage(self.brief, self.homepage.replace('</article></div>',
                '</article><article data-story-card data-kind="news" data-key="event:one"></article></div>'))
        with patch('verify_live_news_coverage.validate_complete_export',
                   return_value=(self.release, self.relationship)):
            with self.assertRaisesRegex(ValueError, 'not bound'):
                verify({}, {**self.brief, 'source_release_sha256': 'stale'}, self.homepage)


if __name__ == '__main__':
    unittest.main()
