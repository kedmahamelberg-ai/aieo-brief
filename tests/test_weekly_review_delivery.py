import copy
import hashlib
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from weekly_review_delivery import (REPOSITORY, approved_file, email_content,
                                    install_approval, load_draft, owner_approved, review_images)


class WeeklyReviewDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = json.loads((Path(__file__).resolve().parents[1] /
                                   'data/weekly-overviews/approved/2026-W41.json').read_text())
        for kind in ('markets', 'research'):
            self.fixture[kind].pop('human_approved', None)
        self.draft = {
            'schema_version': 'aieo_weekly_review_draft_v1',
            'release_id': '2026-W41', 'period_start': '2026-10-05',
            'period_end': '2026-10-11', 'publication_blocked': True,
            'email_blocked': True, 'requires_human_approval': True,
            'overview': {
                'release_id': '2026-W41', 'editorial_status': 'ready',
                'markets': self.fixture['markets'], 'research': self.fixture['research'],
            },
        }
        self.reviews = [{'state': 'approved', 'user': {'login': 'kedmahamelberg-ai', 'id': 209744145},
                         'environments': [{'name': 'weekly-editorial'}]}]

    def test_exact_digest_and_checked_draft_required(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'draft.json'
            path.write_text(json.dumps(self.draft))
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(load_draft(path, digest)['release_id'], '2026-W41')
            with self.assertRaisesRegex(ValueError, 'changed'):
                load_draft(path, '0' * 64)
            changed = copy.deepcopy(self.draft)
            changed['overview']['markets']['review_checks']['grounded'] = False
            path.write_text(json.dumps(changed))
            with self.assertRaises(ValueError):
                load_draft(path, hashlib.sha256(path.read_bytes()).hexdigest())

    def test_only_owner_environment_approval_installs_marker(self):
        self.assertTrue(owner_approved(self.reviews))
        for change in ({'state': 'rejected'}, {'user': {'login': 'someone-else', 'id': 10}},
                       {'environments': [{'name': 'github-pages'}]}):
            bad = [{**self.reviews[0], **change}]
            self.assertFalse(owner_approved(bad))
            with self.assertRaises(ValueError):
                approved_file(self.draft, bad, datetime.now(timezone.utc))
        accepted = approved_file(self.draft, self.reviews, datetime.now(timezone.utc))
        self.assertTrue(accepted['markets']['human_approved'])
        self.assertTrue(accepted['research']['human_approved'])
        self.assertEqual(accepted['approved_by'], 'kedmahamelberg-ai')

    def test_new_owner_approval_archives_stale_edition(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / 'data/weekly-overviews/approved/2026-W41.json'
            path.parent.mkdir(parents=True)
            previous = copy.deepcopy(self.fixture)
            previous['markets']['source_hashes'] = {'stale': 'old'}
            old_bytes = json.dumps(previous).encode()
            path.write_bytes(old_bytes)
            with patch('weekly_review_delivery.ROOT', root), \
                 patch('weekly_review_delivery.review_history', return_value=self.reviews), \
                 patch('weekly_review_delivery.validate_live_sources'):
                self.assertEqual(install_approval(self.draft, '123'), path)
                with self.assertRaisesRegex(ValueError, 'already has an approval'):
                    install_approval(self.draft, '123')
            archive = path.parent / 'archive' / ('2026-W41-' + hashlib.sha256(old_bytes).hexdigest()[:12] + '.json')
            self.assertEqual(archive.read_bytes(), old_bytes)
            self.assertEqual(json.loads(path.read_text())['markets']['source_hashes'],
                             self.draft['overview']['markets']['source_hashes'])

    def test_review_email_accepts_checked_weekly_photo(self):
        overview = copy.deepcopy(self.draft['overview'])
        overview['research']['image_path'] = 'assets/weekly-overviews/milky-way-yellowstone.jpg'
        images = review_images(overview, Path(__file__).resolve().parents[1])
        self.assertEqual(images['research']['content_type'], 'image/jpeg')

    def test_email_shows_plain_prose_and_named_source_links_and_pending_has_no_approval(self):
        url = 'https://github.com/' + REPOSITORY + '/actions/runs/123'
        ready = email_content(self.draft, url)
        self.assertIn('Review and approve on GitHub', ready['html'])
        self.assertIn('Request corrections on GitHub', ready['html'])
        self.assertIn('https://brief.hamelberg-ai.com/story/', ready['html'])
        self.assertIn('Read the reporting', ready['html'])
        self.assertIn('Read the research', ready['html'])
        self.assertIn(self.fixture['research']['papers'][0]['original_headline'], ready['html'])
        linked_part = next(part for paragraph in self.fixture['research']['prose']
                           for part in paragraph if part['source_key'])
        self.assertNotIn('>' + linked_part['text'] + '</a>', ready['html'])
        self.assertIn('src="cid:brief-weekly-markets"', ready['html'])
        self.assertIn('src="cid:brief-weekly-research"', ready['html'])
        self.assertEqual({item['content_id'] for item in ready['attachments']},
                         {'brief-weekly-markets', 'brief-weekly-research'})
        self.assertIn('image_credit', self.fixture['markets'])
        preview = email_content(self.draft, url, image_mode='data')
        self.assertIn('src="data:image/jpeg;base64,', preview['html'])
        self.assertEqual(preview['attachments'], [])
        pending = copy.deepcopy(self.draft)
        pending['requires_human_approval'] = False
        pending['overview']['editorial_status'] = 'pending'
        pending['overview']['markets'] = {'status': 'pending', 'title': 'News pending',
                                          'pending_reason': 'editorial_check_pending'}
        message = email_content(pending, url)
        self.assertNotIn('Review and approve on GitHub', message['html'])
        self.assertIn('editorial_check_pending', message['html'])
        self.assertEqual(len(message['attachments']), 1)


if __name__ == '__main__':
    unittest.main()
