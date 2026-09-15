"""Image-led, public story feed for the creator's website; no social API needed."""
import re
from urllib.parse import urljoin
from story_photos import photo_registry, story_photo

NAMES={'CA':'Canada','CN':'China','FR':'France','GB':'United Kingdom','US':'United States'}

def spotlight_feed(root, stories, baseurl, release_id, generated_at):
    registry=photo_registry(root)
    eligible=[s for s in stories if re.fullmatch(r'story/[a-zA-Z0-9_-]+/index.html', s.get('path','')) and s.get('headline') and s.get('key')]
    selected=[]
    # Keep the daily lead, then offer different discovery markets before filling.
    if eligible:selected.append(eligible[0])
    for market in NAMES:
        candidate=next((s for s in eligible if market in s.get('markets',[]) and s not in selected),None)
        if candidate:
            selected.append(candidate)
    selected.extend(s for s in eligible if s not in selected)
    items=[]
    used=set()
    for story in selected:
        photo=story_photo(story,registry)
        if not photo or photo['sha256'] in used:continue
        market=photo['market']
        used.add(photo['sha256'])
        items.append({'id':story['key'],'headline':story['headline'],'summary':story.get('deck',''),
            'url':urljoin(baseurl+'/',story['path']),'date':story.get('date',''),
            'market':NAMES[market], 'image':urljoin(baseurl+'/',photo['path']),
            'image_alt':photo['alt'],'image_credit':photo['credit'],'image_source':photo['source_url']})
        if len(items)==8:break
    return {'version':1,'release_id':release_id,'updated_at':generated_at,'items':items}
