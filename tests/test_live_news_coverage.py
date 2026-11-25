import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from brief_contract import relationship_fingerprint
from validate_public_site import validate_home_news_coverage
from verify_live_news_coverage import BRIEF, verify, verify_article_routes, verify_story_page


class LiveNewsCoverage(unittest.TestCase):
    def route_fixture(self):
        def story(key):
            return {'event_id': key, 'has_editorial': True, 'path': f'story/{key}/index.html',
                    'headline': f'Headline {key}', 'what_happened': f'Account {key}.',
                    'body_paragraphs': [f'Detail {key}.'],
                    'sources': [{'url': f'https://publisher.example/{key}'}]}
        current, retained = story('current'), story('retained')
        pages = {BRIEF + f'story/{key}/':
                 f'<h1>Headline {key}</h1><p>Account {key}.</p><p>Detail {key}.</p>'
                 f'<a href="https://publisher.example/{key}">Source</a>'
                 for key in ('current', 'retained')}
        return {'stories': [current], 'recent_news': [retained]}, pages

    def route_response(self, url, pages):
        return SimpleNamespace(url=url, text=pages[url], raise_for_status=lambda: None)

    def test_current_and_retained_articles_are_checked_at_the_ordinary_reader_url(self):
        brief, pages = self.route_fixture()
        with patch('verify_live_news_coverage.requests.Session') as factory:
            session = factory.return_value.__enter__.return_value
            session.get.side_effect = lambda url, **kwargs: self.route_response(url, pages)
            self.assertEqual(verify_article_routes(brief), 2)
        self.assertEqual({call.args[0] for call in session.get.call_args_list}, set(pages))
        for call in session.get.call_args_list:
            self.assertEqual(call.kwargs, {'timeout': (10, 30)})

    def test_all_broken_articles_are_reported_including_a_retained_missing_body(self):
        brief, pages = self.route_fixture()
        pages[BRIEF + 'story/retained/'] = pages[BRIEF + 'story/retained/'].replace('<p>Detail retained.</p>', '')
        pages[BRIEF + 'story/current/'] = pages[BRIEF + 'story/current/'].replace('https://publisher.example/current', 'https://wrong.example/')
        with patch('verify_live_news_coverage.requests.Session') as factory:
            session = factory.return_value.__enter__.return_value
            session.get.side_effect = lambda url, **kwargs: self.route_response(url, pages)
            with self.assertRaises(ValueError) as caught:
                verify_article_routes(brief)
        error = str(caught.exception)
        self.assertIn('2 of 2 live news article routes failed', error)
        self.assertIn('current: Live article current is missing its saved source URL', error)
        self.assertIn('retained: Live article retained is missing its saved body_paragraphs', error)

    def test_a_retained_article_redirecting_to_the_publisher_fails(self):
        brief, pages = self.route_fixture()
        def response(url, **kwargs):
            result = self.route_response(url, pages)
            if url == BRIEF + 'story/retained/':
                result.url = 'https://publisher.example/retained'
            return result
        with patch('verify_live_news_coverage.requests.Session') as factory:
            factory.return_value.__enter__.return_value.get.side_effect = response
            with self.assertRaisesRegex(ValueError, 'retained: News route redirects outside the Brief'):
                verify_article_routes(brief)

    def test_live_data_cannot_claim_an_article_when_its_route_lacks_the_body(self):
        story = {'event_id': 'one', 'headline': 'The central development',
                 'what_happened': 'The checked account.', 'body_paragraphs': ['The supported detail.'],
                 'sources': [{'url': 'https://publisher.example/story'}]}
        html = ('<h1>The central development</h1><p>The checked account.</p>'
                '<p>The supported detail.</p><a href="https://publisher.example/story">Source</a>')
        verify_story_page(story, html)
        with self.assertRaisesRegex(ValueError, 'missing its saved body_paragraphs'):
            verify_story_page(story, html.replace('<p>The supported detail.</p>', ''))
        with self.assertRaisesRegex(ValueError, 'missing its saved source URL'):
            verify_story_page(story, html.replace('https://publisher.example/story', 'https://wrong.example/'))
        with self.assertRaisesRegex(ValueError, 'redirects instead'):
            verify_story_page(story, '<meta http-equiv="refresh" content="0;url=https://publisher.example/story">'+html)

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
                                                     'has_editorial': False, 'path':'story/one/index.html',
                                                     'sources': [{'url': 'https://publisher.example/story'}]}],
                      'complete_content': {'eligible_event_ids': ['one']}}
        self.homepage = ('<div id="story-feed"><article class="feed-story" data-story-card '
                         'data-kind="news" data-key="event:one" data-editorial-status="source-only">'
                         '<h2><a href="story/one/">Report</a></h2>'
                         '</article></div>')

    def test_source_only_report_remains_visible_and_counted(self):
        with patch('verify_live_news_coverage.validate_complete_export',
                   return_value=(self.release, self.relationship)):
            result = verify({}, self.brief, self.homepage)
        self.assertEqual((result['observatory_developments'], result['brief_records'],
                          result['rendered_news_cards'], result['full_brief_articles']), (1, 1, 1, 0))

    def test_headline_cards_cannot_hide_missing_source_ready_articles(self):
        self.brief['stories'][0]['evidence_complete'] = True
        with patch('verify_live_news_coverage.validate_complete_export',
                   return_value=(self.release, self.relationship)):
            with self.assertRaisesRegex(ValueError, 'still lack a completed Brief article'):
                verify({}, self.brief, self.homepage)

    def test_earlier_articles_cannot_displace_the_current_batch(self):
        self.brief['recent_news']=[{'key':'event:old','event_id':'old','has_editorial':True,
                                  'what_happened':'Earlier account','body_paragraphs':['Earlier detail']}]
        old='<article data-story-card data-kind="news" data-key="event:old" data-editorial-status="complete" hidden><h2><a href="story/old/">Earlier</a></h2></article>'
        current_first=self.homepage.replace('</div>',old+'</div>')
        self.assertEqual(validate_home_news_coverage(self.brief,current_first)['recent_full_brief_articles'],1)
        with self.assertRaisesRegex(ValueError,'Current edition news must appear before'):
            validate_home_news_coverage(self.brief,self.homepage.replace('<div id="story-feed">','<div id="story-feed">'+old))
        with self.assertRaisesRegex(ValueError,'Earlier articles must be hidden'):
            validate_home_news_coverage(self.brief,current_first.replace(' hidden>','>'))

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
