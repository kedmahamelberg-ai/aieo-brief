import sys
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from short_links import article_alias, short_link_routes

class ShortLinksTests(unittest.TestCase):
    def setUp(self):
        self.path='story/development-example/index.html'
        self.item={'path':self.path}
        self.entry={'slug':'26w38-1l','article_path':self.path,'tracking':{'utm_source':'linkedin','utm_medium':'organic_social','utm_campaign':'brief_2026_w38','utm_content':'MON_NEWS_US_PLAN'}}
    def test_old_alias_survives_more_articles_and_changed_order(self):
        first=short_link_routes([self.item],[], 'https://brief.example')
        second=short_link_routes([{'path':'research/paper-new/index.html'},self.item],[], 'https://brief.example')
        self.assertEqual(first[article_alias(self.path)],second[article_alias(self.path)])
    def test_exact_article_and_attribution(self):
        result=short_link_routes([self.item],[self.entry], 'https://brief.example')
        url=urlsplit(result['s/26w38-1l/index.html']['destination'])
        self.assertEqual(url.path,'/'+self.path)
        self.assertEqual(parse_qs(url.query),{k:[v] for k,v in self.entry['tracking'].items()})
    def test_missing_article_and_duplicate_fail_build(self):
        with self.assertRaises(ValueError):short_link_routes([], [self.entry], 'https://brief.example')
        with self.assertRaises(ValueError):short_link_routes([self.item], [self.entry,self.entry], 'https://brief.example')
    def test_no_external_redirect_or_path_traversal(self):
        for path in ['https://evil.example/', '../index.html', 'story/../../index.html']:
            with self.assertRaises(ValueError):article_alias(path)
