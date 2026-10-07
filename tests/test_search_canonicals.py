from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from search_metadata import canonical_local


class CanonicalLinks(unittest.TestCase):
    def test_home_and_nested_pages_link_to_preferred_directory(self):
        self.assertEqual(canonical_local('index.html'),'./')
        self.assertEqual(canonical_local('index.html','../../'),'../../')
        self.assertEqual(canonical_local('about/index.html','../../'),'../../about/')
        self.assertEqual(canonical_local('story/a/index.html#conversation','../'),'../story/a/#conversation')
        self.assertEqual(canonical_local('research/index.html?q=math','../'),'../research/?q=math')

    def test_assets_and_feed_are_unchanged(self):
        for path in ('assets/site.css','assets/index.html.jpg','feed.xml','data/current.json'):
            self.assertEqual(canonical_local(path,'../'),'../'+path)


if __name__=='__main__':unittest.main()
