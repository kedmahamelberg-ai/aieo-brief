import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from article_urls import assign_article_urls, title_slug
from short_links import article_alias, short_link_routes


def story(key='one', headline='AI models improve science but reliability limits remain'):
    return dict(key=key, kind='news', headline=headline,
                path=f'story/development-{key}/index.html', slug=f'development-{key}')


class ArticleURLTests(unittest.TestCase):
    def test_distilled_example_and_accents(self):
        self.assertEqual(title_slug('AI‑Driven Social Science Gains Highlighted at Beijing Conference, Yet Limits Noted by Organizers'),
                         'ai-driven-social-science-gains-beijing-conference-limits-organizers')
        self.assertEqual(title_slug('Montréal: AI & public services!'), 'montreal-ai-public-services')
        self.assertEqual(title_slug('the and of'), '')

    def test_migration_keeps_keys_and_old_links(self):
        item = story()
        old = copy.deepcopy(item)
        assign_article_urls([item], [old])
        self.assertEqual(item['key'], old['key'])
        self.assertIn(old['path'], item['legacy_paths'])
        self.assertNotIn('development-', item['path'])
        campaign = dict(slug='26w38-1l', article_path=old['path'], tracking=dict(
            utm_source='linkedin', utm_medium='organic_social', utm_campaign='week', utm_content='news'))
        routes = short_link_routes([item], [campaign], 'https://brief.example')
        self.assertEqual(routes[article_alias(old['path'])]['article_path'], item['path'])
        self.assertEqual(routes['s/26w38-1l/index.html']['article_path'], item['path'])
        self.assertIn('utm_source=linkedin', routes['s/26w38-1l/index.html']['destination'])

    def test_second_build_and_headline_edit_keep_canonical(self):
        first = story()
        assign_article_urls([first], [])
        second = story(headline='Entirely different revised headline')
        assign_article_urls([second], [first])
        self.assertEqual(second['path'], first['path'])
        self.assertEqual(second['legacy_paths'], first['legacy_paths'])

    def test_collisions_are_deterministic_and_existing_paths_reserved(self):
        items = [story('two'), story('one')]
        reversed_items = copy.deepcopy(items[::-1])
        assign_article_urls(items, [])
        assign_article_urls(reversed_items, [])
        self.assertEqual({i['key']: i['path'] for i in items}, {i['key']: i['path'] for i in reversed_items})
        self.assertEqual(len({i['path'] for i in items}), 2)
        newcomer = story('three')
        assign_article_urls([newcomer], items)
        self.assertNotIn(newcomer['path'], {i['path'] for i in items})

    def test_research_and_pending_translation(self):
        paper = dict(story(), kind='research', path='research/paper-one/index.html')
        pending = dict(story('two'), english_status='pending')
        assign_article_urls([paper, pending], [])
        self.assertTrue(paper['path'].startswith('research/ai-'))
        self.assertEqual(pending['path'], 'story/development-two/index.html')
        self.assertNotIn('url_slug_version', pending)

    def test_unsafe_or_reused_alias_fails(self):
        with self.assertRaises(ValueError):
            assign_article_urls([dict(story(), legacy_paths=['../outside/index.html'])], [])
        with self.assertRaises(ValueError):
            assign_article_urls([story(), dict(story('two'), path=story()['path'])], [])


if __name__ == '__main__':
    unittest.main()
