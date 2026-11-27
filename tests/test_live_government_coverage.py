import sys
import unittest
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from government_briefs import fingerprint, monitor_record
from verify_live_government_coverage import verify, verify_article_page, sync_held_issue


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
                      'monitor_as_of': self.snapshot['as_of'],
                      'last_checked_at': '2026-11-23T09:00:00Z',
                      'records': {'lu-item': self.record}, 'checked': {'lu-item': sha}}
        self.public_item = {**self.record, 'deck': self.record['summary'], 'key': 'government-card-key',
                            'announcement_paragraphs': [self.record['summary']]}
        self.public = {'government_count': 1, 'governments': [self.public_item]}
        self.sync = '<p id="government-sync" data-monitor-as-of="2026-11-23T08:00:00Z" data-last-checked="2026-11-23T09:00:00Z"></p>'
        self.card = '<article class="feed-story government-card" data-key="government-card-key" data-date="2026-11-22"></article>'
        self.html = self.sync + self.card

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
            verify(self.snapshot, self.state, self.public, self.sync)

    def test_duplicate_live_card_fails(self):
        with self.assertRaisesRegex(ValueError, 'duplicates'):
            verify(self.snapshot, self.state, self.public, self.sync + self.card + self.card)

    def test_stale_monitor_snapshot_or_missing_visible_check_fails(self):
        self.snapshot['as_of'] = '2026-11-24T08:00:00Z'
        with self.assertRaisesRegex(ValueError, 'latest Monitor snapshot'):
            verify(self.snapshot, self.state, self.public, self.html)
        self.snapshot['as_of'] = self.state['monitor_as_of']
        with self.assertRaisesRegex(ValueError, 'does not show the saved Monitor check time'):
            verify(self.snapshot, self.state, self.public, self.card)

    def test_held_ai_item_is_reported_but_not_published(self):
        held = {**self.item, 'id': 'held-ai', 'classification_status': 'needs_review'}
        self.snapshot['items'].append(held)
        report = verify(self.snapshot, self.state, self.public, self.html)
        self.assertEqual(report['monitor_ai_held_for_review'], 1)
        self.assertEqual(report['held_ids'], ['held-ai'])

    def test_held_ai_issue_is_not_reposted_when_unchanged(self):
        held = {**self.item, 'id': 'held-ai', 'classification_status': 'needs_review'}
        snapshot = {'items': [held]}
        class Response:
            def __init__(self, value): self.value = value
            def raise_for_status(self): pass
            def json(self): return self.value
        class Session:
            def __init__(self, existing=None):
                self.headers = {}
                self.existing = existing
                self.writes = []
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def get(self, *_args, **_kwargs): return Response([self.existing] if self.existing else [])
            def post(self, _url, json, **_kwargs):
                self.writes.append(('post', json))
                return Response({})
            def patch(self, _url, json, **_kwargs):
                self.writes.append(('patch', json))
                return Response({})
        first = Session()
        with patch.dict('os.environ', {'GITHUB_TOKEN': 'test-token', 'GITHUB_REPOSITORY': 'owner/brief'}), patch('verify_live_government_coverage.requests.Session', return_value=first):
            sync_held_issue(snapshot)
        self.assertEqual([kind for kind, _ in first.writes], ['post'])
        unchanged = Session({'title': 'Government AI labels held for source review', 'body': first.writes[0][1]['body'], 'url': 'https://api.github.com/repos/owner/brief/issues/1'})
        with patch.dict('os.environ', {'GITHUB_TOKEN': 'test-token', 'GITHUB_REPOSITORY': 'owner/brief'}), patch('verify_live_government_coverage.requests.Session', return_value=unchanged):
            sync_held_issue(snapshot)
        self.assertEqual(unchanged.writes, [])

    def test_correct_input_hash_cannot_hide_generated_saved_body(self):
        self.record['body_paragraphs'] = ['An older generated AI claim.']
        with self.assertRaisesRegex(ValueError, 'mechanically reuse Monitor body_paragraphs'):
            verify(self.snapshot, self.state, self.public, self.html)

    def test_live_generated_body_fails_even_when_card_and_ids_match(self):
        self.public_item['announcement_paragraphs'] = ['An older generated AI claim.']
        with self.assertRaisesRegex(ValueError, 'stale announcement paragraphs'):
            verify(self.snapshot, self.state, self.public, self.html)

    def article_html(self):
        return ('<article id="article-content"><header><div class="story-kicker">Luxembourg</div>'
                '<h1>Luxembourg launches an AI marketplace.</h1>'
                '<time datetime="2026-11-22">22 November 2026</time></header>'
                '<section aria-labelledby="announcement"><h2>What was announced</h2>'
                '<p>Luxembourg launched an AI-supported marketplace.</p></section>'
                '<a href="https://example.lu/ai" data-source-link>Official source</a></article>')

    def test_complete_live_article_matches_monitor(self):
        verify_article_page(self.public_item, self.record, self.article_html())

    def test_article_body_and_source_must_be_on_the_reader_page(self):
        for old, new, message in (
                ('Luxembourg launched an AI-supported marketplace.', 'Old generated claim.', 'Monitor body'),
                ('https://example.lu/ai', 'https://wrong.example/ai', 'source link'),
                ('datetime="2026-11-22"', 'datetime="2026-11-21"', 'date'),
                ('<article id="article-content">', '<article>', 'no article content')):
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                verify_article_page(self.public_item, self.record, self.article_html().replace(old, new))

    def test_source_redirect_cannot_replace_the_article(self):
        with self.assertRaisesRegex(ValueError, 'redirects'):
            verify_article_page(self.public_item, self.record,
                                '<meta http-equiv="refresh" content="0;url=https://example.lu/ai">')

    def test_unsupported_addition_to_an_otherwise_correct_headline_fails(self):
        with self.assertRaisesRegex(ValueError, 'headline'):
            verify_article_page(self.public_item, self.record,
                                self.article_html().replace('</h1>', ' AI systems deployed nationwide.</h1>'))

    def test_extra_wrong_source_link_fails_even_when_the_correct_link_exists(self):
        with self.assertRaisesRegex(ValueError, 'source link'):
            verify_article_page(self.public_item, self.record,
                                self.article_html().replace('</article>',
                                    '<a data-source-link href="https://wrong.example/ai">Wrong</a></article>'))


if __name__ == '__main__':
    unittest.main()
