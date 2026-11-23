import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from check_saved_news import newly_available, publication_busy


class SavedNews(unittest.TestCase):
    def test_only_new_finished_articles_trigger_publication(self):
        def row(eid, complete):
            return {'event_id': eid, 'has_editorial': complete,
                    'what_happened': 'Account' if complete else '',
                    'body_paragraphs': ['Checked detail'] if complete else []}
        self.assertEqual(newly_available([row('old', True), row('new', True), row('pending', False)],
                                        {'stories': [row('old', True), row('new', False)]}), ['new'])
        self.assertEqual(newly_available([row('old', True)], {'stories': [row('old', True)]}), [])

    def test_an_active_publisher_is_not_duplicated(self):
        self.assertTrue(publication_busy([{'name': 'Build and Publish AIEO Brief',
                                          'status': 'queued'}], lambda url: []))
        run = {'name': 'Follow Observatory Editions', 'status': 'in_progress', 'jobs_url': 'jobs'}
        self.assertFalse(publication_busy([run], lambda url: [{'name': 'editorial / update', 'status': 'in_progress'}]))
        self.assertTrue(publication_busy([run], lambda url: [{'name': 'publish / build', 'status': 'in_progress'}]))


if __name__ == '__main__':
    unittest.main()
