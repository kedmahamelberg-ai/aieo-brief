import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from spotlight import spotlight_feed
ROOT=Path(__file__).resolve().parents[1]
class SpotlightTests(unittest.TestCase):
    def test_only_exact_public_story_routes_are_exposed(self):
        stories=[{'key':'good','path':'story/good/index.html','headline':'A <headline>','markets':['US'],'date':'2026-09-15'},
                 {'key':'bad','path':'https://untrusted.example/','headline':'Bad','markets':['US']}]
        feed=spotlight_feed(ROOT,stories,'https://brief.hamelberg-ai.com','2026-W38','2026-09-15')
        self.assertEqual(len(feed['items']),1)
        self.assertEqual(feed['items'][0]['url'],'https://brief.hamelberg-ai.com/story/good/index.html')
        self.assertEqual(feed['items'][0]['headline'],'A <headline>')
        self.assertTrue((ROOT/'assets/spotlight/us.jpg').is_file())
    def test_missing_market_does_not_get_a_misleading_photo(self):
        self.assertEqual(spotlight_feed(ROOT,[{'key':'a','path':'story/a/index.html','headline':'A','markets':[]}],'https://brief.hamelberg-ai.com','week','today')['items'],[])
