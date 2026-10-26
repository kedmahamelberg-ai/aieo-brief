"""Produce review-only social assets from a successfully deployed news edition.

No model API, social account, scheduling, or publishing credentials are used.
"""
import argparse
import hashlib
import html
import json
import os
import re
import subprocess
import time
import zipfile
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode, urlparse
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
ZONE = ZoneInfo('Europe/Amsterdam')
BASE = 'https://brief.hamelberg-ai.com/'
STATUS = 'DRAFT_NOT_APPROVED_DO_NOT_PUBLISH'
COUNTRIES = {'US': 'United States', 'CA': 'Canada', 'GB': 'United Kingdom', 'FR': 'France', 'CN': 'China'}
GEO = dict(US='#USAI', CA='#CanadaAI', GB='#UKAI', FR='#FranceAI', CN='#ChinaAI')
ACCOUNTS = {'linkedin': 'The Brief | AI Empowerment Observatory Page, company 146490147', 'facebook': 'The Brief | AI Empowerment Observatory Page, profile 61594324679612', 'instagram': 'thebrief_ai.empowerment', 'substack_note': 'The Brief publication, @thebriefaieo'}


def read(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def fetch(url, output=None):
    args = ['curl', '--fail', '--silent', '--show-error', '--location', '--max-time', '60', '--retry', '3', '--retry-delay', '2', '-A', 'TheBriefSocialReview/1.0', url]
    if output:
        subprocess.run(args + ['-o', str(output)], check=True)
        return
    return subprocess.check_output(args)


def edition(items):
    news = [i for i in items if i.get('kind') == 'news' and i.get('period_end')]
    if not news:
        raise ValueError('No published news edition')
    end = max(i['period_end'] for i in news)
    current = [i for i in news if i['period_end'] == end]
    ids = {i['edition'] for i in current}
    starts = {i['period_start'] for i in current}
    if len(ids) != 1 or len(starts) != 1:
        raise ValueError('Inconsistent edition metadata')
    start, end_date = date.fromisoformat(next(iter(starts))), date.fromisoformat(end)
    if start.weekday() != 0 or end_date - start != timedelta(days=6):
        raise ValueError('Expected complete Monday through Sunday coverage')
    monday = end_date + timedelta(days=1)
    return next(iter(ids)), start, end_date, monday, current


def due(items, state, today):
    release, start, end, monday, news = edition(items)
    if end >= today:
        raise ValueError('Coverage period has not ended')
    # Never catch up an obsolete edition as if it were this week's content.
    if today >= monday + timedelta(days=7):
        return False, release
    return release not in state.get('editions', {}), release


def clean(text):
    return re.sub(r'\s+', ' ', html.unescape(re.sub('<[^>]+>', '', str(text or '')))).strip().replace('–', ', ').replace('—', ', ').replace(':', ',')


def topic_plan(items, monday, news):
    """Select an even five-market draft; no missing market is silently replaced."""
    target = {k: 3 for k in COUNTRIES}
    target[list(COUNTRIES)[monday.isocalendar().week % 5]] = 2
    pools = {}
    for market in COUNTRIES:
        pools[market] = [i for i in news if market in i.get('markets', []) and i.get('what_happened') and i.get('body_paragraphs') and i.get('sources') and not any('_localized_' in str(p) for p in i.get('body_paragraphs', []))]
        pools[market].sort(key=lambda i: (not i.get('has_editorial'), -date.fromisoformat(i['date']).toordinal(), i['path']))
    topics, used, counts, previous = [], set(), Counter(), None
    for n in range(14):
        available = [m for m in COUNTRIES if counts[m] < target[m] and any(a['path'] not in used for a in pools[m])]
        if not available:
            raise ValueError('Insufficient distinct source-backed news for all five markets')
        market = min(available, key=lambda m: (m == previous, counts[m], list(COUNTRIES).index(m)))
        a = next(a for a in pools[market] if a['path'] not in used)
        used.add(a['path']); counts[market] += 1; previous = market
        day = monday + timedelta(days=n // 2); hour = '10:00' if n % 2 == 0 else '18:00'
        ident = day.strftime('%a').upper() + hour[:2] + '_' + market + '_' + hashlib.sha256(a['path'].encode()).hexdigest()[:8].upper()
        topics.append({'id': ident, 'date': str(day), 'time': hour, 'kind': 'News', 'country': COUNTRIES[market], 'market': market, 'path': a['path'], 'headline': clean(a['headline']), 'hook': clean(a.get('deck') or a['headline']), 'fact': clean(a['what_happened']), 'tags': ['#TheBrief', '#ResponsibleAI', GEO[market]], 'second_subject_tag': '#AIGovernance', 'evidence': 'Published source-backed Brief reporting', 'source_urls': [s['url'] for s in a['sources']], 'source_limitation': a.get('limitation', ''), 'market_rationale': 'Source edition market assignment; confirm subject geography during editorial review', 'substack_lead': 'From this week’s Brief, a closer look at how AI is being used.'})
    if counts != Counter(target):
        raise ValueError('The five-market balance is incomplete')
    research = [i for i in items if i.get('kind') == 'research' and str(monday - timedelta(days=7)) <= i.get('date', '') < str(monday) and i.get('what_happened') and i.get('sources')]
    if not research:
        raise ValueError('No current source-backed Research item')
    a = max(research, key=lambda i: (i['date'], i['path']))
    topics.append({'id': 'WED06_RESEARCH', 'date': str(monday + timedelta(days=2)), 'time': '06:00', 'kind': 'Research', 'country': '', 'market': '', 'path': a['path'], 'headline': clean(a['headline']), 'hook': clean(a.get('deck') or a['headline']), 'fact': clean(a['what_happened']), 'tags': ['#TheBrief', '#AIResearch', '#ResearchCommunity'], 'second_subject_tag': '#MachineLearning', 'evidence': clean(a.get('research_label', 'Research')) + ', ' + clean(a.get('summary_basis', 'Evidence scope requires review')), 'source_urls': [s['url'] for s in a['sources']], 'source_limitation': a.get('limitation', ''), 'substack_lead': 'The research selection examines the evidence behind the result.'})
    return sorted(topics, key=lambda t: (t['date'], t['time']))


def new_photos(topics, history, output):
    """Use only Commons public-domain/CC0 photos, with permanent duplicate history."""
    old_urls = set(history.get('source_urls', [])); old_hashes = set(history.get('sha256', []))
    queries = {'US': 'New York skyline photograph', 'CA': 'Canada landscape photograph', 'GB': 'London skyline photograph', 'FR': 'Paris cityscape photograph', 'CN': 'Shanghai skyline photograph'}
    photos = {}
    for market, query in queries.items():
        selected = [t for t in topics if t['kind'] == 'News' and t['market'] == market]
        params = dict(action='query', generator='search', gsrsearch=query+' -painting -drawing -map', gsrnamespace=6, gsrlimit=100, prop='imageinfo', iiprop='url|size|mime|extmetadata', iiurlwidth=1400, format='json')
        data = json.loads(fetch('https://commons.wikimedia.org/w/api.php?' + urlencode(params)))
        candidates = sorted(data.get('query', {}).get('pages', {}).values(), key=lambda p: p.get('index', 999))
        for topic in selected:
            for page in candidates:
                info = page.get('imageinfo', [{}])[0]; meta = info.get('extmetadata', {})
                license = meta.get('LicenseShortName', {}).get('value')
                url = info.get('descriptionurl', '')
                if license not in ('Public domain', 'CC0') or info.get('mime') != 'image/jpeg' or min(info.get('width', 0), info.get('height', 0)) < 900 or url in old_urls:
                    continue
                title = page['title'].removeprefix('File:')
                if re.search(r'\b(painting|drawing|map|engraving|lithograph|illustration)\b', title, re.I):
                    continue
                path = output/'sources'/f"{topic['id']}.jpg"
                try:
                    fetch(info.get('thumburl') or info['url'], path)
                except subprocess.CalledProcessError:
                    continue
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                if digest in old_hashes:
                    continue
                topic['photo'] = topic['id']
                photos[topic['photo']] = {'title': title, 'creator': clean(meta.get('Artist', {}).get('value')), 'archive': 'Wikimedia Commons', 'source_url': url, 'download_url': info.get('thumburl') or info['url'], 'rights_status': license, 'local_source': 'sources/'+path.name, 'sha256': digest, 'duplicate_check': 'PASS, URL and SHA-256 absent from permanent history', 'verified_on': str(datetime.now(ZONE).date()), 'use': 'Illustrative country photograph; editorial visual review required'}
                old_urls.add(url); old_hashes.add(digest)
                break
            else:
                raise ValueError('No fresh rights-cleared photograph for '+topic['id'])
    return photos


def header(t):
    return 'The brief AI research' if t['kind'] == 'Research' else 'The brief AI news from '+t['country']


def curated_photos(photos, history, output, archive):
    """Use the reviewed bytes, not a CDN thumbnail that can be re-encoded."""
    with zipfile.ZipFile(archive) as bundle:
        for photo in photos.values():
            if photo['source_url'] in history['source_urls'] or photo['sha256'] in history['sha256']:
                raise ValueError('Curated photo already used by another batch')
            relative = Path(photo['local_source'])
            if relative.is_absolute() or '..' in relative.parts or relative.parts[0] != 'sources':
                raise ValueError('Invalid curated photo path')
            data = bundle.read(relative.as_posix())
            if hashlib.sha256(data).hexdigest() != photo['sha256']:
                raise ValueError('Reviewed photo archive content changed')
            (output / relative).write_bytes(data)


def cta(t):
    return 'Read the research briefing on The Brief.' if t['kind'] == 'Research' else 'Read the full story on The Brief.'


def render(topics, photos, output):
    from PIL import Image, ImageDraw, ImageFont, ImageOps
    paper, green = '#f6f3ec', '#123b32'
    candidates = ['/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', '/System/Library/Fonts/Supplemental/Arial Bold.ttf']
    fontpath = next((p for p in candidates if Path(p).exists()), None)
    if not fontpath:
        raise ValueError('A scalable font is required')
    def block(draw, text, box, max_size=54, fill=green):
        x,y,w,h=box
        for size in range(max_size, 21, -2):
            font=ImageFont.truetype(fontpath,size); lines=[]; line=''
            for word in text.split():
                trial=(line+' '+word).strip()
                if draw.textbbox((0,0),trial,font=font)[2]>w and line:lines.append(line);line=word
                else:line=trial
            if line:lines.append(line)
            lineheight=int(size*1.3)
            if len(lines)*lineheight<=h:break
        else:raise ValueError('Copy does not fit the artwork; editorial shortening required')
        for line in lines:draw.text((x,y),line,font=font,fill=fill);y+=lineheight
    logo=Image.open(ROOT/'assets/favicon-512.png').convert('RGBA');logo.thumbnail((115,115))
    for t in topics:
        for n,text in enumerate([t['hook'],t['fact'],cta(t)],1):
            im=Image.new('RGB',(1080,1350),paper);d=ImageDraw.Draw(im)
            if n==1 and t['kind']=='News':
                photo=Image.open(output/photos[t['photo']]['local_source']).convert('RGB')
                im.paste(ImageOps.fit(photo,(1080,650)),(0,250));d.rectangle((0,900,1080,1350),fill=green)
                block(d,text,(65,935,950,310),fill=paper)
            else:block(d,text,(65,380,950,700),max_size=60 if n==1 else 50)
            if n==1 and t['kind']=='Research':
                d.rectangle((65,1080,1015,1195),fill=green)
                block(d,t['evidence'],(95,1100,890,80),30,paper)
            im.paste(logo,(45,50),logo)
            if t['kind']=='News':
                block(d,'The brief AI news from',(190,55,820,60),36)
                block(d,t['country'].upper(),(190,115,820,100),58)
            else:block(d,header(t),(190,65,820,100),43)
            block(d,'brief.hamelberg-ai.com',(65,1260,780,55),25, paper if n==1 and t['kind']=='News' else green)
            im.save(output/'assets'/f"{t['id']}_carousel_{n}.png")
            story=Image.new('RGB',(1080,1920),paper);story.paste(im,(0,240))
            ImageDraw.Draw(story).text((65,1740),f'{n} / 3',font=ImageFont.truetype(fontpath,32),fill=green)
            story.save(output/'assets'/f"{t['id']}_story_{n}.png")


def build(topics, photos, output, release, start, end, monday):
    week=monday.strftime('%G-W%V'); campaign='brief_'+week.lower().replace('-','_');items=[]
    for t in topics:
        if not re.fullmatch(r'(story|research)/[a-z0-9-]+/(index\.html)?',t['path']):raise ValueError('Unsafe article path')
        dt=datetime.fromisoformat(t['date']+'T'+t['time']+':00').replace(tzinfo=ZONE).isoformat()
        slides=[str((output/'assets'/f"{t['id']}_carousel_{n}.png").resolve()) for n in (1,2,3)]
        for platform,account in ACCOUNTS.items():
            url=BASE+t['path']+'?'+urlencode(dict(utm_source=platform,utm_medium='organic_social',utm_campaign=campaign,utm_content=t['id']))
            tags=t['tags'] if platform=='linkedin' else t['tags'][:2]
            if platform=='instagram':tags=['#TheBrief','#AIBriefResearch' if t['kind']=='Research' else '#AIBriefNews',t['tags'][1],t['second_subject_tag'],t['tags'][2]]
            pieces=[header(t),t['hook'],t['fact'],cta(t)]
            if platform=='substack_note':pieces.insert(1,t['substack_lead'])
            if platform!='instagram':pieces.append(url)
            pieces.append(' '.join(tags))
            i=dict(id=t['id']+'_'+platform,topic_id=t['id'],platform=platform,account=account,scheduled_at=dt,status=STATUS,caption='\n\n'.join(pieces),visible_link=url if platform!='instagram' else None,resolved_destination=url,feed_asset=slides[0],prepared_carousel_assets=slides if platform in ('facebook','instagram') else slides[:1],media_type='photo_carousel' if platform in ('facebook','instagram') else 'single_image',photo_rights=photos.get(t.get('photo')),evidence_status=t['evidence'],music_enabled=False)
            if platform=='linkedin':i['single_image_asset']=slides[0]
            if platform=='instagram':i['story']=dict(scheduled_at=dt,frames=[str((output/'assets'/f"{t['id']}_story_{n}.png").resolve()) for n in (1,2,3)],link_stickers_enabled=False,article_destination=url,music_enabled=False)
            items.append(i)
    post={'status':STATUS,'proposed_at':datetime.combine(monday,datetime.min.time(),tzinfo=ZONE).replace(hour=12).isoformat(),'title':'This week in The Brief','body':'This edition follows AI across five markets, with people and institutions deciding how it should be used. Start with these source-linked stories.\n\n'+'\n\n'.join(t['hook']+'\n'+BASE+t['path'] for t in topics[::3]),'destination':BASE+'?'+urlencode(dict(utm_source='substack_post',utm_medium='organic_social',utm_campaign=campaign))}
    return dict(schema_version='aieo_social_batch_v4',source_edition=release,source_dates=f'{start} to {end}',publishing_week=week,timezone='Europe/Amsterdam',status=STATUS,approval_phrase='APPROVE SOCIAL WEEK '+week,topics=topics,items=items,substack_post=post,editorial_review_required=True)


def verify_links(batch):
    checks=[]
    for url in sorted({i['resolved_destination'] for i in batch['items']}):
        body=fetch(url).decode('utf-8');topic=next(t for t in batch['topics'] if BASE+t['path']==url.split('?')[0])
        # HTTP 200 alone does not prove the destination is the selected article.
        if '<h1' not in body or topic['path'].split('/')[1] not in body:
            raise ValueError('Article route/content did not match '+url)
        checks.append(dict(url=url,ok=True,http_status=200))
    return dict(all_ok=True,checked_at=datetime.now(ZONE).isoformat(),results=checks)


def review(batch, output):
    lines=['# The Brief social approval batch '+batch['publishing_week'],'','**DRAFT. NOT APPROVED. DO NOT PUBLISH.**','','Source coverage '+batch['source_dates']+'. All dates use Europe/Amsterdam.','','LinkedIn uses one image. Facebook and Instagram carousels must appear in this exact order: 1 cover/photo and headline, 2 explanation, 3 CTA. Upload each carousel image separately and wait for Meta to finish processing it before adding the next. After scheduling or publishing, reopen the saved post and check all three cards in order; a correct composer preview is not sufficient. If the saved order is wrong, create and verify a replacement before moving the wrong scheduled copy to Drafts. Stories use photo/headline, explanation, CTA. Music and stickers are omitted. Exact tracked URLs are the fallback until approved short aliases are imported.','','## Editorial review','', 'Review copy, featured geography, photo relevance and claims before approval. Country photos are illustrative. No generated images or paid model calls are used. Draft tags reflect source topics and require search-interest review.','']
    for t in batch['topics']:
        lines+=['## '+t['id'],'',t['date']+' '+t['time']+' Amsterdam','',f"[Article]({BASE+t['path']})",'',t['evidence'],'',t.get('source_limitation',''),'']
        if t.get('photo'):
            p=batch['items'][next(n for n,i in enumerate(batch['items']) if i['topic_id']==t['id'])]['photo_rights']
            lines += [f"Photo {p['title']} by {p['creator']}. {p['rights_status']}. [Rights source]({p['source_url']}). SHA-256 `{p['sha256']}`.",'']
        lines += [f"![Photo/headline](assets/{t['id']}_carousel_1.png)",f"![Explanation](assets/{t['id']}_carousel_2.png)",f"![CTA](assets/{t['id']}_carousel_3.png)",'']
        for i in [i for i in batch['items'] if i['topic_id']==t['id']]:
            lines+=['### '+i['platform'],'',i['account'],'',i['caption'],'']
            if i['platform']=='instagram':
                lines+=['Internal article reference '+i['resolved_destination'],'','Matching three-frame Story at the same Amsterdam time. No link stickers.','']
    lines += ['## Weekly Substack Post','',batch['substack_post']['title'],'',batch['substack_post']['body'],'','## Approval','',batch['approval_phrase'],'','Approval authorizes overdue slots to publish as soon as practical and future slots to be scheduled through the organization accounts. This package itself does not publish or schedule anything.']
    (output/'BATCH_REVIEW.md').write_text('\n'.join(lines))


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'social-review');p.add_argument('--check-only',action='store_true');p.add_argument('--record',action='store_true');a=p.parse_args()
    statepath=ROOT/'data/social-production/state.json';state=read(statepath,{'editions':{}})
    if a.record:
        batch=read(a.output/'batch.json');ready=read(a.output/'READY_FOR_REVIEW.json');assert ready and ready['status']==STATUS
        artifact=os.environ.get('SOCIAL_ARTIFACT_URL');assert artifact and artifact.startswith('https://github.com/')
        history=read(ROOT/'config/social-photo-history.json',{'source_urls':[],'sha256':[]})
        for photo in read(a.output/'PHOTO_MANIFEST.json').values():
            for field,key in [('source_url','source_urls'),('sha256','sha256')]:history[key]=sorted(set(history[key]+[photo[field]]))
        state['editions'][batch['source_edition']]={'publication_week':batch['publishing_week'],'status':STATUS,'artifact_url':artifact,'run_id':os.environ.get('GITHUB_RUN_ID'),'created_at':datetime.now(ZONE).isoformat()}
        save(statepath,state);save(ROOT/'config/social-photo-history.json',history);return
    expected_path=os.environ.get('EXPECTED_ITEMS')
    expected=edition(read(Path(expected_path))['items'])[0] if expected_path else None
    for attempt in range(6):
        items=json.loads(fetch(BASE+'data/public-items.json'))['items']
        if expected is None or edition(items)[0]==expected:break
        if attempt==5:raise ValueError('Live site has not reached the deployed news edition; do not produce stale drafts')
        time.sleep(10)
    needed,release=due(items,state,datetime.now(ZONE).date())
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'],'a') as f:f.write('needed='+str(needed).lower()+'\n')
    print(json.dumps({'production_needed':needed,'release_id':release}))
    if a.check_only or not needed:return
    release,start,end,monday,news=edition(items);output=a.output.resolve()
    for name in ['assets','sources']: (output/name).mkdir(parents=True,exist_ok=True)
    (output/'READY_FOR_REVIEW.json').unlink(missing_ok=True)
    curated=read(ROOT/'config'/f'social-{release}.json')
    topics=curated['topics'] if curated else topic_plan(items,monday,news)
    for t in topics:
        current=next((i for i in items if i.get('path')==t['path']),None)
        if not current or (t['kind']=='News' and current.get('edition')!=release):raise ValueError('Selected article is not in the deployed edition')
    history=read(ROOT/'config/social-photo-history.json',{'source_urls':[],'sha256':[]})
    if curated:
        photos=curated['photos']
        curated_photos(photos, history, output, ROOT/'config'/f'social-photos-{release}.zip')
    else:photos=new_photos(topics,history,output)
    if len(photos)!=14 or len({p['sha256'] for p in photos.values()})!=14:raise ValueError('Fourteen distinct photographs required')
    save(output/'PHOTO_MANIFEST.json',photos);save(output/'topics.json',topics)
    render(topics,photos,output);batch=build(topics,photos,output,release,start,end,monday)
    if curated and curated.get('substack_post'):
        batch['substack_post']=curated['substack_post']
    from validate_social_package import validate
    errors=validate(batch)
    if errors:raise ValueError('\n'.join(errors))
    save(output/'batch.json',batch);save(output/'LINK_CHECK.json',verify_links(batch));review(batch,output)
    # Portable downloaded artifacts must not retain runner-specific absolute paths.
    prefix=str(output)+'/'
    portable=json.loads(json.dumps(batch).replace(prefix,''));save(output/'batch.json',portable)
    save(output/'READY_FOR_REVIEW.json',{'status':STATUS,'publication_week':batch['publishing_week'],'editorial_review_required':True,'checks':['prepared media','copy fields','link responses','photo rights','photo duplicates'],'created_at':datetime.now(ZONE).isoformat()})
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as f:f.write('## Social review '+batch['publishing_week']+'\n\nDraft package produced after website deployment. Download the social-review artifact and review BATCH_REVIEW.md. **No posts published or scheduled.**\n\n'+batch['approval_phrase']+'\n')


if __name__=='__main__':main()
