"""One rights-cleared, story-keyed photo source for pages, carousel and social."""
import hashlib
import json
from pathlib import Path

def photo_registry(root):
    data=json.loads((Path(root)/'config/story-photos.json').read_text())
    for photo in data['photos'].values():
        if not photo.get('license') or not photo.get('source_url') or not (Path(root)/photo['path']).is_file():
            raise ValueError('A story photograph is missing rights or its local asset')
        photo['sha256']=hashlib.sha256((Path(root)/photo['path']).read_bytes()).hexdigest()
    return data

def story_photo(story, registry):
    pinned=registry['stories'].get(story.get('path'))
    if pinned:return registry['photos'][pinned]
    # Stable per article, independent of daily order and build time.
    markets=story.get('markets',[])
    candidates=[p for p in registry['photos'].values() if p['market'] in markets]
    if not candidates:return None
    seed=int(hashlib.sha256(story['path'].encode()).hexdigest(),16)
    return candidates[seed % len(candidates)]

def assert_distinct_story_photos(stories, registry):
    used={}
    for story in stories:
        photo=story_photo(story,registry)
        if not photo:raise ValueError('Select a rights-cleared photo for '+story['path'])
        digest=photo['sha256']
        if digest in used and used[digest]!=story['path']:
            raise ValueError('Different stories reuse one photograph: '+used[digest]+' and '+story['path'])
        used[digest]=story['path']

if __name__ == '__main__':
    import argparse
    parser=argparse.ArgumentParser(description='Check distinct rights-cleared photos for a social News batch')
    parser.add_argument('batch', type=Path)
    args=parser.parse_args()
    batch=json.loads(args.batch.read_text())
    news=[s for s in batch['topics'] if s.get('kind')=='News']
    if not news:raise SystemExit('No News topics found')
    assert_distinct_story_photos(news,photo_registry(Path(__file__).resolve().parents[1]))
    print(f'Validated {len(news)} News articles: no duplicate photographs')
