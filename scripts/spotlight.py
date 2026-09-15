"""Image-led, public story feed for the creator's website; no social API needed."""
import json
import re
from pathlib import Path
from urllib.parse import urljoin

NAMES={'CA':'Canada','CN':'China','FR':'France','GB':'United Kingdom','US':'United States'}

def spotlight_feed(root, stories, baseurl, release_id, generated_at):
    photos=json.loads((Path(root)/'config/spotlight-photos.json').read_text())
    eligible=[s for s in stories if re.fullmatch(r'story/[a-zA-Z0-9_-]+/index.html', s.get('path','')) and s.get('headline') and s.get('key')]
    selected=[]
    chosen_market={}
    # Keep the daily lead, then offer different discovery markets before filling.
    if eligible:selected.append(eligible[0])
    for market in NAMES:
        candidate=next((s for s in eligible if market in s.get('markets',[]) and s not in selected),None)
        if candidate:
            selected.append(candidate)
            chosen_market[candidate["key"]]=market
    selected.extend(s for s in eligible if s not in selected)
    items=[]
    for story in selected:
        market=chosen_market.get(story['key']) or next((m for m in story.get('markets',[]) if m in photos),None)
        if not market:continue
        photo=photos[market]
        items.append({'id':story['key'],'headline':story['headline'],'summary':story.get('deck',''),
            'url':urljoin(baseurl+'/',story['path']),'date':story.get('date',''),
            'market':NAMES[market], 'image':urljoin(baseurl+'/',photo['path']),
            'image_alt':photo['alt'],'image_credit':photo['credit'],'image_source':photo['source_url']})
        if len(items)==8:break
    return {'version':1,'release_id':release_id,'updated_at':generated_at,'items':items}
