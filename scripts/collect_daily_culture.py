#!/usr/bin/env python3
"""Daily attributed art, poetry, prose, quotations and licensed music.

This is curation of existing works, not invented attribution or synthetic news.
Source dates and reuse information travel with each item. Remote failures keep
previous published items and cannot masquerade as a fresh successful selection.
"""
from __future__ import annotations
import argparse,hashlib,html,json,re,time
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
from urllib.parse import quote,urlparse
import requests
ROOT=Path(__file__).resolve().parents[1]
CACHE=ROOT/'.cache/culture'
POETS={'Emily Dickinson':1886,'William Blake':1827,'William Wordsworth':1850,'Christina Rossetti':1894,'John Keats':1821,'Percy Bysshe Shelley':1822,'Walt Whitman':1892,'Ralph Waldo Emerson':1882}
EXCLUDE=re.compile(r'\b(?:nigger|niggers|negro|negroes|faggot|porn|pornography|rape|suicide|suicidal|murder|massacre|slaughter|sexual|nude|nudity|bootleg|podcast|fuck|fucking|pussy|pornographic|newborn babes|dined off)\b',re.I)
CC=re.compile(r'^https?://creativecommons\.org/(?:licenses/(?:by|by-sa)/(?:2\.0|2\.5|3\.0|4\.0)|publicdomain/(?:zero|mark)/1\.0)/?$')

def clean(value):
    if isinstance(value,list):value=' · '.join(str(v) for v in value)
    return re.sub(r'\s+',' ',html.unescape(re.sub('<[^>]+>',' ',str(value or '')))).strip()
def key(value):return 'culture:'+hashlib.sha256(value.encode()).hexdigest()[:24]
def sha(value):return hashlib.sha256(value.encode()).hexdigest()
def get(url,params=None,maximum=4_000_000):
    if urlparse(url).scheme!='https':raise ValueError('Sources must use HTTPS')
    for attempt in range(2):
        try:
            response=requests.get(url,params=params,headers={'User-Agent':'AIEO-Brief/3.1 (daily cultural selection; https://observatory.hamelberg-ai.com)'},timeout=(10,25),stream=True)
            response.raise_for_status();chunks=[];size=0
            for chunk in response.iter_content(65536):
                size+=len(chunk)
                if size>maximum:raise ValueError('Source exceeds collection size limit')
                chunks.append(chunk)
            response._content=b''.join(chunks);response.encoding='utf-8';return response
        except requests.RequestException:
            if attempt:raise
            time.sleep(2)
def cached_json(name,url,params=None,days=7):
    CACHE.mkdir(parents=True,exist_ok=True);path=CACHE/(name+'.json')
    if path.exists() and time.time()-path.stat().st_mtime<days*86400:return json.loads(path.read_text())
    data=get(url,params).json();path.write_text(json.dumps(data,ensure_ascii=False));return data
def licence(value):
    value=clean(value)
    if not CC.fullmatch(value):return None
    value=value.replace('http://','https://').rstrip('/')+'/'
    label='CC0' if '/zero/' in value else 'Public domain mark' if '/mark/' in value else 'CC BY-SA '+value.split('/')[-2] if '/by-sa/' in value else 'CC BY '+value.split('/')[-2]
    return {'label':label,'url':value,'basis':'Source-declared licence','changes':'Presented without alteration; display size may vary.'}
def record(kind,identity,title,author,url,origin,rights,**extra):
    if not all((title,author,url,rights)) or not url.startswith('https://'):raise ValueError('Missing attribution or reuse information')
    return {'key':key(identity),'culture_type':kind,'headline':clean(title),'creator':clean(author),'source_url':url,'publisher':origin,'rights':rights,**extra}
def pick(rows,day,recent):
    rows=[r for r in rows if not EXCLUDE.search(r['headline']+' '+r.get('excerpt',''))]
    fresh=[r for r in rows if r['key'] not in recent]
    if not fresh:raise ValueError('No fresh eligible work in this source selection')
    return sorted(fresh,key=lambda r:sha(day+r['key']))[0]

def illustration(day,recent,settings):
    # Prefer a CC0 collection with explicit creator death dates and a small web image.
    params={'cc0':1,'has_image':1,'type':'Drawing','limit':30,'skip':(date.fromisoformat(day).toordinal()%20)*30}
    data=cached_json('cleveland-'+str(params['skip']),'https://openaccess-api.clevelandart.org/api/artworks/',params)
    rows=[]
    for item in data.get('data',[]):
        creators=item.get('creators') or [];media=((item.get('images') or {}).get('web') or {}).get('url','')
        if item.get('share_license_status')!='CC0' or not media.startswith('https://openaccess-cdn.clevelandart.org/'):continue
        if not creators or any(not re.fullmatch(r'\d{4}',str(c.get('death_year',''))) or int(c['death_year'])>1935 for c in creators):continue
        if not item.get('creation_date_latest') or item['creation_date_latest']>1925:continue
        creator=' · '.join(clean(c['description']) for c in creators)
        rights={'label':'CC0 image','url':'https://creativecommons.org/publicdomain/zero/1.0/','basis':'Cleveland Museum of Art open-access record; CC0 image. All named creators died before 1936.','changes':'Image displayed at a reduced size without cropping.','credit':clean(item.get('creditline'))}
        rows.append(record('illustration','cleveland:'+str(item['id']),item['title'],creator,item['url'],'Cleveland Museum of Art',rights,work_date=clean(item['creation_date']),media_url=media,alt=clean(item['title'])+' by '+creator,deck='A drawing from the museum’s open collection. Take a closer look, then explore the work and its artist.'))
    chosen=pick(rows,day,recent);response=get(chosen['media_url'],maximum=2_500_000)
    if not response.content.startswith(b'\xff\xd8\xff'):raise ValueError('Image source did not return a JPEG')
    name=chosen['key'].split(':')[1]+'.jpg';path=ROOT/'assets/culture'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(response.content)
    chosen['image_path']='assets/culture/'+name;return chosen

def poetry(day,recent,settings):
    authors=settings['poets'];offset=date.fromisoformat(day).toordinal()%len(authors);rows=[]
    for author in (authors[offset],authors[(offset+1)%len(authors)]):
        if author not in POETS or POETS[author]>1900:continue
        data=cached_json('poet-'+sha(author)[:10],'https://poetrydb.org/author/'+quote(author,safe=''))
        if not isinstance(data,list):continue
        for p in data:
            lines=p.get('lines',[]);text='\n'.join(lines)
            if p.get('author')!=author or not 5<=len([l for l in lines if l.strip()])<=28 or len(text.split())>220:continue
            if EXCLUDE.search(text):continue
            rights={'label':'Public-domain poem','url':'https://poetrydb.org/index.html','basis':'Original English text; author died '+str(POETS[author])+'.','changes':'Poem text and line breaks retained as supplied by PoetryDB.'}
            rows.append(record('poetry','poetrydb:'+author+':'+p['title'],p['title'],author,'https://poetrydb.org/title/'+quote(p['title'],safe='')+':abs/lines.text','PoetryDB',rights,work_date='Historical poem',poem_lines=lines,excerpt=text,deck='A poem by '+author+'. Read it at your own pace.'))
        time.sleep(2)
    return pick(rows,day,recent)

def book_text(book):
    if book['author_death']>1935 or book['publication_year']>1910:raise ValueError('Book outside the vetted public-domain shelf')
    CACHE.mkdir(parents=True,exist_ok=True);cache=CACHE/f'book-{book["id"]}.txt'
    if cache.exists() and time.time()-cache.stat().st_mtime<30*86400:return cache.read_text()
    bid=str(book['id']);relative='/'.join(bid[:-1])+'/'+bid+'/'+bid+'-0.txt'
    urls=['https://gutenberg.pglaf.org/cache/epub/'+bid+'/pg'+bid+'.txt','https://mirror.cs.odu.edu/gutenberg/'+relative]
    for url in urls:
        try:
            text=get(url).text
            if 'START OF THE PROJECT GUTENBERG' not in text.upper() and 'START OF THIS PROJECT GUTENBERG' not in text.upper():continue
            cache.write_text(text);time.sleep(2);return text
        except requests.RequestException:continue
    raise ValueError('No readable copy from a permitted Gutenberg mirror')
def passages(raw,body_start=None):
    pieces=re.split(r'\*\*\*\s*START OF (?:THE|THIS) PROJECT GUTENBERG[^\n]*\n',raw,flags=re.I)
    if len(pieces)<2:raise ValueError('Missing book start marker')
    body=re.split(r'\*\*\*\s*END OF (?:THE|THIS) PROJECT GUTENBERG',pieces[1],flags=re.I)[0]
    if body_start:
        # Last heading match skips the contents list. Never quote an editor’s preface as the author.
        matches=list(re.finditer(r'^\s*'+re.escape(body_start)+r'[^\n]*$',body,flags=re.M|re.I))
        if not matches:raise ValueError('Expected work heading missing; no unattributed front matter selected')
        body=body[matches[-1].end():]
    result=[]
    for part in re.split(r'\n\s*\n',body):
        value=clean(part)
        if not 75<=len(value.split())<=210 or not re.search(r'[.!?][”\"\']?$',value):continue
        if EXCLUDE.search(value) or re.search(r'Gutenberg|transcrib|ISBN|copyright|illustration|contents|^chapter|^preface|^produced',value,re.I):continue
        result.append(value)
    return result
def quotable_sentences(value):
    return [s for s in re.split(r'(?<=[.!?])\s+',value) if 6<=len(s.split())<=25 and not any(mark in s for mark in ('“','”','"','_')) and re.search(r'[.!?]$',s)]

def literature(day,recent,settings):
    books=settings['books'];offset=date.fromisoformat(day).toordinal()%len(books);last_error=None
    for book in (books[offset],books[(offset+1)%len(books)]):
        try:
            texts=passages(book_text(book),book.get('body_start'));texts=[p for p in texts if re.search(r'\b(?:art|beauty|flowers?|garden|river|trees?|morning|friend|music|imagination|wonder|leaves|birds?|sunshine|nature|creativ|joy)\b',p,re.I)];rights={'label':'Public-domain text','url':'https://www.gutenberg.org/ebooks/'+str(book['id']),'basis':'Original English edition; published '+str(book['publication_year'])+'; author died '+str(book['author_death'])+'.','changes':'One complete paragraph selected; paragraph whitespace normalised.'}
            rows=[record('text','gutenberg:'+str(book['id'])+':'+sha(p),book['title']+' · a short reading',book['author'],'https://www.gutenberg.org/ebooks/'+str(book['id']),'Project Gutenberg',rights,work_date=str(book['publication_year']),excerpt=p,deck='A short passage from '+book['title']+' ('+str(book['publication_year'])+'), by '+book['author']+'.') for p in texts]
            rows=[r for r in rows if quotable_sentences(r['excerpt'])]
            item=pick(rows,day,recent)
            sentences=re.split(r'(?<=[.!?])\s+',item['excerpt'])
            quotes=quotable_sentences(item['excerpt'])
            if not quotes:continue
            sentence=sorted(quotes,key=lambda s:sha(day+s))[0]
            q=record('quote','quotation:'+str(book['id'])+':'+sha(sentence),sentence,book['author'],item['source_url'],'Project Gutenberg',{**rights,'changes':'A complete sentence quoted from the linked text.'},work_date=str(book['publication_year']),excerpt=sentence,quote_context=item['excerpt'],deck='From '+book['title']+' ('+str(book['publication_year'])+').')
            if q['key'] in recent:continue
            return item,q
        except (requests.RequestException,ValueError) as error:last_error=error
    raise ValueError('No fresh complete passage and attributed quotation available') from last_error

def duration(value):
    try:
        parts=str(value).split(':');n=0.0
        for part in parts:n=n*60+float(part)
        return round(n)
    except (TypeError,ValueError):return 0
def cc_mixter_music(day,recent,settings):
    # ccMixter's artist-published API supplies explicit licences and sample credits.
    tag=settings.get('music_tags',['instrumental','song'])[date.fromisoformat(day).toordinal()%2]
    deadline=time.monotonic()+210
    offset=(date.fromisoformat(day).toordinal()%30)*5
    rows=[]
    for source_tag,source_offset in [('instrumental',0),(tag,offset)]:
        try:
            batch=cached_json('music-'+source_tag+'-'+str(source_offset),'https://ccmixter.org/api/query',{'f':'json','limit':5,'offset':source_offset,'tags':source_tag,'lic':'by'},days=1)
            if isinstance(batch,list):rows.extend(batch)
        except (requests.RequestException,ValueError):continue
    if not isinstance(rows,list):raise ValueError('Music API did not return a list')
    options=[]
    for item in rows:
        rights=licence(item.get('license_url'));extra=item.get('upload_extra') or {}
        if not rights or extra.get('nsfw') is not False or not item.get('user_name'):continue
        title=clean(item.get('upload_name'));creator=clean(item.get('user_real_name') or item['user_name'])
        if EXCLUDE.search(title+' '+clean(item.get('upload_description_plain'))):continue
        for f in item.get('files') or []:
            seconds=duration((f.get('file_format_info') or {}).get('ps'));media=f.get('download_url','')
            if not media.startswith('https://ccmixter.org/content/') or not media.lower().endswith('.mp3') or not 45<=seconds<=600:continue
            if int(f.get('file_rawsize') or 0)>20_000_000:continue
            identity='ccmixter:'+str(item['upload_id'])+':'+str(f['file_id'])
            if key(identity) in recent:continue
            rights['changes']='Original audio, without edits. Creator and source credits retained.'
            r=record('music',identity,title,creator,item['file_page_url'],'ccMixter',rights,work_date=clean(item.get('upload_date_format')),media_url=media,duration_seconds=seconds,featuring=clean(extra.get('featuring')),deck='Music by '+creator+'. '+str(seconds//60)+':'+f'{seconds%60:02d}'+' to listen.',upload_id=item['upload_id'])
            options.append(r)
    while options and time.monotonic()<deadline:
        chosen=pick(options,day,recent)
        try:
            # Follow the declared sample tree, with a bounded limit; no silent loss of credits.
            credits=[];seen={chosen['upload_id']};queue=[chosen['upload_id']]
            while queue:
                if len(seen)>15 or time.monotonic()>deadline:raise ValueError('Music credit checking exceeded its bounded pass')
                upload=queue.pop(0);time.sleep(1)
                sources=cached_json('music-credits-'+str(upload),'https://ccmixter.org/api/query',{'f':'json','sources':upload,'limit':5})
                if not isinstance(sources,list) or len(sources)>=5:raise ValueError('Incomplete music credits')
                for source in sources:
                    lic=licence(source.get('license_url'))
                    if not lic:raise ValueError('A music component has incompatible or missing reuse terms')
                    sid=source['upload_id']
                    if sid in seen:continue
                    seen.add(sid);queue.append(sid)
                    credits.append({'title':clean(source['upload_name']),'creator':clean(source.get('user_real_name') or source['user_name']),'url':source['file_page_url'],'license_url':lic['url'],'license_label':lic['label']})
            chosen['credits']=credits;chosen.pop('upload_id');verify_audio(chosen['media_url']);return chosen
        except (requests.RequestException,ValueError,KeyError):options=[r for r in options if r['key']!=chosen['key']]
    raise ValueError('No fresh playable music with complete commercial-use credits')

def verify_audio(url):
    # Reuse a successful same-day stream check; never download the full track.
    CACHE.mkdir(parents=True,exist_ok=True);check=CACHE/('audio-check-'+sha(url)[:16]+'.json')
    if check.exists():
        saved=json.loads(check.read_text())
        if saved.get('date')==date.today().isoformat() and saved.get('url')==url and saved.get('http_status')==200:return
    with requests.get(url,headers={'User-Agent':'AIEO-Brief/3.1'},timeout=(8,18),stream=True) as r:
        r.raise_for_status();head=next(r.iter_content(1024),b'')
        if not head or not ('audio' in r.headers.get('Content-Type','') or head.startswith(b'ID3') or head[:1]==b'\xff'):raise ValueError('Music URL did not return audio')
        check.write_text(json.dumps({'date':date.today().isoformat(),'url':url,'http_status':200,'content_type':r.headers.get('Content-Type')}))

def archive_music(day,recent,settings):
    # Artist names form a small configurable shelf, not unrestricted reuploads.
    creators=settings.get('archive_music_creators',['Jess Bottles'])
    def candidates():
        # This artist-published original recording is also available if discovery is offline.
        yield {'identifier':'GoodLightShine'}
        query='mediatype:audio AND ('+' OR '.join('creator:"'+name.replace('"','')+'"' for name in creators)+')'
        try:
            data=cached_json('archive-artists-'+sha(query)[:10],'https://archive.org/advancedsearch.php',{'q':query,'rows':30,'output':'json','fl[]':['identifier','title','creator'],'sort[]':'date desc'},days=1)
            docs=sorted(data.get('response',{}).get('docs',[]),key=lambda x:sha(day+x['identifier']))
            yield from docs[:5]
        except (requests.RequestException,ValueError):return
    deadline=time.monotonic()+160
    for doc in candidates():
        if time.monotonic()>deadline:break
        try:
            detail=cached_json('archive-record-'+sha(doc['identifier'])[:12],'https://archive.org/metadata/'+quote(doc['identifier'],safe=''))
            meta=detail.get('metadata',{});author=clean(meta.get('creator'));rights=licence(meta.get('licenseurl'))
            if not rights or not any(name.lower() in author.lower() for name in creators):continue
            if EXCLUDE.search(clean(meta.get('title'))):continue
            rows=[]
            files=[f for f in detail.get('files',[]) if f.get('name','').lower().endswith('.mp3')]
            # Prefer named works over duplicate unnamed demo/derivative files.
            named=[f for f in files if f.get('title')]
            for f in named or files:
                name=f.get('name','');seconds=duration(f.get('length'))
                if not name.lower().endswith('.mp3') or not 45<=seconds<=600 or int(f.get('size') or 0)>20_000_000:continue
                title=clean(f.get('title') or meta.get('title'))
                if EXCLUDE.search(title) or re.search(r'\b(?:cover|tribute|karaoke)\b',title,re.I):continue
                ident='archive:'+doc['identifier']+':'+name
                if key(ident) in recent:continue
                rights={**rights,'changes':'Original audio, without edits. Credit retained from the artist’s source record.'}
                media='https://archive.org/download/'+quote(doc['identifier'],safe='')+'/'+quote(name,safe='')
                rows.append(record('music',ident,title,author,'https://archive.org/details/'+quote(doc['identifier'],safe=''),'Internet Archive',rights,work_date=clean(meta.get('date'))[:10] or 'Date not supplied',media_url=media,duration_seconds=seconds,album=clean(meta.get('title')),credits=[],deck='Music by '+author+'. '+str(seconds//60)+':'+f'{seconds%60:02d}'+' to listen.'))
            for chosen in sorted(rows,key=lambda r:sha(day+r['key']))[:3]:
                if time.monotonic()>deadline:break
                try:verify_audio(chosen['media_url']);return chosen
                except (requests.RequestException,ValueError):continue
        except (requests.RequestException,ValueError,KeyError,TypeError):continue
    raise ValueError('No accessible licensed track from the configured artist shelf')

def music(day,recent,settings):
    try:return archive_music(day,recent,settings)
    except (requests.RequestException,ValueError,KeyError):return cc_mixter_music(day,recent,settings)

def main():
    p=argparse.ArgumentParser();p.add_argument('--date',default=date.today().isoformat());p.add_argument('--refresh',action='store_true');a=p.parse_args();day=date.fromisoformat(a.date).isoformat()
    settings=json.loads((ROOT/'config/culture.json').read_text());target=ROOT/'data/culture';target.mkdir(parents=True,exist_ok=True)
    if not settings.get('enabled'):print('Daily culture is disabled.');return
    public=target/'current.json';old=json.loads(public.read_text()) if public.exists() else {'items':[],'editions':{}}
    if len(old.get('editions',{}).get(day,[]))==5 and not a.refresh:print('This day already has its five published selections.');return
    existing={x['key']:x for x in old.get('items',[])};selected={x['culture_type']:x for x in existing.values() if x['key'] in old.get('editions',{}).get(day,[])}
    recent=set(existing);status=[]
    for name,fn in [('illustration',illustration),('poetry',poetry),('reading_and_quote',literature),('music',music)]:
        types={'text','quote'} if name=='reading_and_quote' else {name}
        if types.issubset(selected):status.append({'source':name,'status':'already_selected'});continue
        try:
            value=fn(day,recent,settings)
            for item in value if isinstance(value,tuple) else (value,):
                item.update(date=day,selected_on=day);selected[item['culture_type']]=item;recent.add(item['key']);existing[item['key']]=item
            status.append({'source':name,'status':'ok'})
        except (requests.RequestException,ValueError,KeyError,TypeError) as e:status.append({'source':name,'status':'unavailable','error_type':type(e).__name__})
    cutoff=(date.fromisoformat(day)-timedelta(days=settings.get('retention_days',45))).isoformat()
    editions={d:ids for d,ids in old.get('editions',{}).items() if d>=cutoff};editions[day]=[x['key'] for x in selected.values()]
    records=[x for x in existing.values() if x['date']>=cutoff]
    if not records:raise SystemExit('No culture sources available. The last published website is retained.')
    payload={'schema_version':'aieo_daily_culture_v1','latest_selection_date':day,'generated_at':datetime.now(timezone.utc).isoformat(),'editions':editions,'items':records,'source_status':status}
    tmp=public.with_suffix('.tmp');tmp.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n');tmp.replace(public)
    summary={'date':day,'new_selection_count':len(selected),'sources':status};(target/'status.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
    # Old pages retain their remote source image if its local cache is pruned.
    keep={Path(x['image_path']).name for x in records if x.get('image_path')}
    for image in (ROOT/'assets/culture').glob('*.jpg'):
        if image.name not in keep:image.unlink()
    import os
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as f:f.write('## Daily culture\n\n'+str(len(selected))+' of 5 selections available for '+day+'. Original authors, dates and reuse information are retained.\n\n'+'\n'.join('- '+x['source']+': '+x['status'] for x in status)+'\n')
    if any(x['status']=='unavailable' for x in status):raise SystemExit(1)
if __name__=='__main__':
    import fcntl
    (ROOT/'.cache').mkdir(exist_ok=True)
    with (ROOT/'.cache/culture-run.lock').open('w') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise SystemExit('A culture update is already running in this checkout.')
        main()
