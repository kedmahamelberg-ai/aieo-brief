from pathlib import Path
import sys
import unittest

from jinja2 import DictLoader, Environment

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from weekly_overviews import engagement_items


class WeeklyEngagementTests(unittest.TestCase):
    def setUp(self):
        self.overview = {
            'release_id': '2026-W42',
            'period_start': '2026-10-12',
            'period_end': '2026-10-18',
            'path': 'week-from-above/2026-w42/index.html',
            'editorial_version': 'test',
            'markets': self.section('markets', 'The week in news'),
            'research': self.section('research', 'The week in research'),
        }
        self.items = engagement_items([self.overview])
        names = ('weekly-overview.html', 'weekly-archive.html', 'weekly-prose.html',
                 'components.html', 'conversation.html')
        templates = {name: (ROOT / 'templates' / name).read_text() for name in names}
        templates['base.html'] = '{% block content %}{% endblock %}'
        self.env = Environment(loader=DictLoader(templates), autoescape=True)

    @staticmethod
    def section(kind, title):
        return {
            'kind': kind, 'status': 'ready', 'author': 'The Brief',
            'title': title, 'deck': 'A source-linked weekly reading.',
            'eyebrow': 'THIS WEEK', 'prose': [[{'text': 'One short paragraph.'}]],
            'scope_note': 'Selected sources only.', 'entries': [], 'papers': [],
            'image_path': 'assets/image.jpg', 'image_alt': 'Landscape',
            'image_source_url': 'https://example.org/image',
            'image_caption': 'Landscape', 'image_credit': 'Museum',
            'image_rights': 'CC0',
        }

    def test_two_stable_items_render_separate_controls_and_conversations(self):
        news, research = self.items
        self.assertEqual((news['key'], research['key']),
                         ('weekly:2026-W42:markets', 'weekly:2026-W42:research'))
        self.assertEqual((news['kind'], research['kind']),
                         ('weekly_news', 'weekly_research'))
        self.assertEqual(engagement_items([self.overview]), self.items)
        html = self.env.get_template('weekly-overview.html').render(
            weekly_page_overview=self.overview,
            weekly_page_period_label='12 Oct - 18 Oct',
            weekly_markets_item=news, weekly_research_item=research,
            local=lambda path: '/' + path,
        )
        for item in self.items:
            self.assertIn(f'data-public-metrics="{item["key"]}"', html)
            self.assertIn(f'data-engagement-key="{item["key"]}"', html)
            self.assertIn(f'id="{item["conversation_anchor"]}"', html)
            self.assertIn(f'#{item["conversation_anchor"]}', html)
        self.assertEqual(html.count('data-comment-form'), 2)
        self.assertEqual(html.count('data-weekly-reading-body'), 2)
        self.assertEqual(html.count('data-action="like"'), 2)
        self.assertEqual(html.count('data-action="save"'), 2)
        self.assertIn('<h1>The week in AI, 12 Oct - 18 Oct</h1>', html)
        self.assertIn('<h2>The week in news</h2>', html)
        self.assertNotIn('<h1>The week in news</h1>', html)

    def test_archive_links_to_both_readings_without_repeating_actions(self):
        html = self.env.get_template('weekly-archive.html').render(
            overview_archive=[self.overview],
            weekly_items_by_key={item['key']: item for item in self.items},
            local=lambda path: '/' + path,
        )
        self.assertIn('The week in news', html)
        self.assertIn('The week in research', html)
        self.assertIn('/week-from-above/2026-w42/index.html#research-compass', html)
        self.assertIn('Read both one-minute views', html)
        self.assertNotIn('class="story-actions"', html)
        self.assertNotIn('class="public-metrics"', html)


if __name__ == '__main__':
    unittest.main()
