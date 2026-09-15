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
    def test_distinct_images_and_stable_story_assignments(self):
        from story_photos import photo_registry,story_photo,assert_distinct_story_photos
        registry=photo_registry(ROOT)
        stories=[{'key':str(n),'path':f'story/test-{n}/index.html','headline':f'News {n}','markets':[m]} for n,m in enumerate(['CN','CN','CN','US','US','US','GB','GB','CA','CA','FR']*8)]
        feed=spotlight_feed(ROOT,stories,'https://brief.hamelberg-ai.com','week','today')
        self.assertEqual(len(feed['items']),8)
        self.assertEqual(len({s['image'] for s in feed['items']}),8)
        for s in stories:
            self.assertEqual(story_photo(s,registry),story_photo(dict(s,date='next week'),registry))
        duplicate=[{'path':'story/same-a/index.html'},{'path':'story/same-b/index.html'}]
        registry['stories'].update({s['path']:'cn' for s in duplicate})
        with self.assertRaises(ValueError):assert_distinct_story_photos(duplicate,registry)
        assert_distinct_story_photos([duplicate[0],duplicate[0]],registry)
    def test_new_edition_uses_new_stories(self):
        def edition(week):return [{'key':week+str(n),'path':f'story/{week}-{n}/index.html','headline':week,'markets':['US','CN','CA','GB','FR']} for n in range(30)]
        a=spotlight_feed(ROOT,edition('w38'),'https://brief.hamelberg-ai.com','w38','today')
        b=spotlight_feed(ROOT,edition('w39'),'https://brief.hamelberg-ai.com','w39','next-week')
        self.assertFalse({s['id'] for s in a['items']} & {s['id'] for s in b['items']})
        self.assertEqual(b['release_id'],'w39')
