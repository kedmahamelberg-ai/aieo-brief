"""One rights-cleared, story-keyed photo source for pages, carousel and social."""
import hashlib
import json
from pathlib import Path

def photo_registry(root):
    data=json.loads((Path(root)/'config/story-photos.json').read_text())
    for photo in data['photos'].values():
        if not photo.get('license') or not photo.get('source_url') or not (Path(root)/photo['path']).is_file():
            raise ValueError('A story photograph is missing rights or its local asset')
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
        digest=photo['source_url']
        if digest in used and used[digest]!=story['path']:
            raise ValueError('Different stories reuse one photograph: '+used[digest]+' and '+story['path'])
        used[digest]=story['path']
