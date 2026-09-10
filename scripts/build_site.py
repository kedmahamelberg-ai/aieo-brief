#!/usr/bin/env python3
"""Build a source-linked Brief and stable historical story pages; private inputs never ship."""
from __future__ import annotations
import argparse, collections, copy, json, os, re, shutil, time
from datetime import datetime, timezone, date
from pathlib import Path
from urllib.parse import urlparse
from xml.sax.saxutils import escape as xml_escape
import requests
from jinja2 import Environment, FileSystemLoader, select_autoescape
from brief_contract import validate_complete_export, validate_pair, load_config, safe_url, digest, relationship_fingerprint, MARKETS, PROMPT_VERSION
from brief_database import dbmaps
from news_notifications import public_settings
from daily_selection import rotation_plan, reading_day
from culture_library import publication as culture_publication, discoveries as culture_discoveries, summary as culture_summary
from english_publication import EnglishPublication, content_version, LAYOUT
from weekly_overviews import prepare_weekly_overviews, social_queue
ROOT=Path(__file__).resolve().parents[1]
SITE=ROOT/'_site'
OBS=os.environ.get('OBSERVATORY_BASE_URL','https://observatory.hamelberg-ai.com').rstrip('/')
TOPICS={'work':'Work & skills','creativity':'Culture & creativity','everyday':'Everyday life','policy':'Rules & rights','technology':'AI & technology','research':'Science & research','business':'Business & investment'}
DIRECTION_LABELS={'gain':'Benefits reported','loss':'Downsides reported','mixed':'Benefits and downsides','none':'No direction stated','unresolved':'Evidence incomplete'}
ISO={'CAN':'CA','CHN':'CN','FRA':'FR','GBR':'GB','USA':'US',**dict((k,k) for k,_ in MARKETS)}

def utc_now(): return datetime.now(timezone.utc).isoformat()
def fetch(url):
    r=requests.get(url,timeout=45);r.raise_for_status();return r.json()
def inputs(preview=False):
    if preview:
        return tuple(json.loads((ROOT/'data/preview'/x).read_text()) for x in ('release.json','symbiosis.json'))
    for attempt in range(3):
        try:
            return validate_complete_export(fetch(f'{OBS}/data/brief/current.json'))
        except (ValueError, requests.RequestException):
            if attempt==2: raise
            time.sleep(2)
def text(value): return re.sub(r'\s+',' ',str(value or '')).replace('—',',').strip()
def fmt(value):
    try: return datetime.fromisoformat(str(value)[:10]).strftime('%d %b %Y').lstrip('0')
    except ValueError: return ''
def public_evidence(value):
    # Audit-process commentary is private, while the actual evidence stays intact.
    sentences=re.split(r'(?<=[.!?])\s+',text(value))
    bad=re.compile(r'old (?:rationale|classification)|earlier (?:rationale|classification)|previous (?:coding|rationale)|supabase|override|reclassif|gold.standard|rubric|stored body|manually|model.cod|coding|codebook',re.I)
    return ' '.join(s for s in sentences if not bad.search(s))
def detect_topic(event):
    raw=text((event.get('classification') or {}).get('topic')).lower()
    value=raw+' '+text(event.get('event_title')).lower()
    for key,terms in [('policy','regulat|polic|law|copyright|govern|rights'),('work','work|job|skill|employ|educat|student|teach|legal'),('creativity','music|creativ|art |film|fiction|culture'),('research','scient|research|study|discovery'),('business','business|invest|profit|stocks|fund|market|valuation|bank')]:
        if re.search(terms,value):return key
    return 'technology' if re.search('model|chip|robot|compute|agent',value) else 'everyday'
def version_valid(version, row, release):
    if not version or version.get('publication_status') not in ('published','preview'):return False
    basis=version.get('evidence_basis_summary') or {}
    return basis.get('prompt_version')==PROMPT_VERSION and basis.get('source_release_sha256')==release.get('content_sha256') and basis.get('axes_sha256')==digest(row.get('axes',{}))

def cards(release,sym,registry,readiness,editorial,preview=False):
    axesmap={r['event_id']:r for r in sym['evidence']}
    marketmap=collections.defaultdict(set)
    for article in (release.get('units') or {}).get('coverage_articles',[]):
        eid=str(article.get('effective_event_id') or article.get('event_id'))
        for country in article.get('search_markets') or []:
            if country in ISO:marketmap[eid].add(ISO[country])
    names=dict(MARKETS);output=[]
    for event in release['evidence']:
        eid=str(event.get('effective_event_id') or event['event_id']);row=axesmap[eid];axes=row['axes']
        reg=registry.get(eid) or {};ready=readiness.get(eid) or {};v=editorial.get(eid)
        if not version_valid(v,row,release):v=None
        for key in ('human','ai'):
            if axes[key]['direction'] not in DIRECTION_LABELS:raise ValueError('Invalid direction')
        sources=[]
        for src in event.get('sources') or []:
            url=safe_url(src.get('url'),allow_http=True)
            if url:sources.append({'publisher':text(src.get('publisher') or src.get('name') or urlparse(url).hostname),'headline':text(src.get('headline')),'url':url,'date':str(src.get('published_date') or '')[:10],'language':src.get('source_language','')})
        if not sources:raise ValueError('A story has no usable source link: '+eid)
        slug=str(reg.get('slug') or 'development-'+eid)
        if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,180}',slug):slug='development-'+eid
        topic=detect_topic(event);market=sorted(marketmap[eid]);original=text(event.get('event_title'))
        if v:
            headline=text(v['editorial_headline']);deck=text(v['editorial_deck'])
            body=[text(p) for p in re.split(r'\n\s*\n',v.get('body_markdown','')) if text(p)]
            happened=text(v.get('what_happened'));why=text(v.get('why_it_matters'))
            basis='AIEO summary'
        else:
            headline=original;body=[];happened='';why=''
            deck=text(event.get('event_summary'))
            if not deck or not axes.get('evidence_complete'):
                deck='Reporting from '+sources[0]['publisher']+'. Open the source for the article.'
            basis='Publisher headline'
        human=public_evidence(axes['human'].get('evidence'));ai=public_evidence(axes['ai'].get('evidence'))
        if v:human=text(v.get('for_humans')) or human;ai=text(v.get('for_ai')) or ai
        count=max(1,round(len((' '.join([happened,why,human,ai,*body])).split())/220))
        output.append({'key':'event:'+eid,'event_id':eid,'kind':'news','slug':slug,'path':f'story/{slug}/index.html','headline':headline,'original_headline':original,'deck':deck,'what_happened':happened,'why_it_matters':why,'body_paragraphs':body,'for_humans':human,'for_ai':ai,'human_direction':axes['human']['direction'],'ai_direction':axes['ai']['direction'],'human_label':DIRECTION_LABELS[axes['human']['direction']],'ai_label':DIRECTION_LABELS[axes['ai']['direction']],'evidence_complete':bool(axes.get('evidence_complete')),'display_scope':text(row.get('display_scope')),'sources':sources,'source_count':len(sources),'publisher':sources[0]['publisher'],'date':str(event.get('event_date') or '')[:10],'display_date':fmt(event.get('event_date')),'markets':market,'market_label':' · '.join(names[c] for c in market) or 'Market not recorded','topic':topic,'topic_label':TOPICS[topic],'reading_minutes':count,'summary_basis':basis,'claim_status':((v or {}).get('evidence_basis_summary') or {}).get('claim_status','reporting'),'limitation':text(((v or {}).get('evidence_basis_summary') or {}).get('limitation')),'has_editorial':bool(v),'edition':release['release_id'],'period_start':release['period_start'],'period_end':release['period_end']})
    return sorted(output,key=lambda c:(c['date'],c['key']),reverse=True)

def papers():
    p=ROOT/'data/research/public.json'
    if not p.exists():return []
    raw=json.loads(p.read_text()).get('papers',[]);out=[]
    for r in raw:
        if not safe_url(r.get('url')):continue
        key=str(r['key'])
        if not re.fullmatch(r'paper:[a-f0-9]{24}',key):raise ValueError('Unsafe paper key')
        slug=key.replace(':','-')
        out.append({**r,'kind':'research','slug':slug,'path':f'research/{slug}/index.html','source_count':1,'sources':[{'publisher':r['publisher'],'headline':r['original_headline'],'url':r['url'],'date':r['date'],'language':'en'}],'display_date':fmt(r['date']),'markets':[],'market_label':'Research','topic':'research','topic_label':TOPICS['research'],'human_direction':'unresolved','ai_direction':'unresolved','for_humans':'','for_ai':'','human_label':'','ai_label':'','evidence_complete':False,'display_scope':'','edition':r['date'][:7],'summary_basis':r.get('summary_basis','Paper reference'),'body_paragraphs':r.get('body_paragraphs',[]),'reading_minutes':max(1,r.get('reading_minutes',1)),'has_editorial':bool(r.get('has_editorial'))})
    return sorted(out,key=lambda x:x['date'],reverse=True)

def culture_items():
    labels={'illustration':'Art & illustration','poetry':'Poetry','text':'A short reading','quote':'A quotation','music':'Music'}
    out=[]
    for r in culture_publication(root=ROOT).get('items',[]):
        if not re.fullmatch(r'culture:[a-f0-9]{24}',r.get('key','')) or r.get('culture_type') not in labels:raise ValueError('Invalid culture record')
        if not safe_url(r.get('source_url')) or not r.get('creator') or not safe_url(r.get('rights',{}).get('url')):raise ValueError('Culture attribution is incomplete')
        slug=r['key'].replace(':','-');image=r.get('image_path','')
        if image and (not re.fullmatch(r'assets/culture/[a-f0-9]{24}\.jpg',image) or not (ROOT/image).is_file()):image=''
        out.append({**r,'creator_origin':r.get('creator_origin') or 'Origin not recorded in the source','image_path':image,'kind':'culture','slug':slug,'path':f'culture/{slug}/index.html','sources':[{'publisher':r['publisher'],'headline':r['headline'],'url':r['source_url'],'date':r.get('work_date',''),'language':r.get('language','')}],'source_count':1,'display_date':fmt(r['date']),'markets':[],'market_label':'Daily culture','topic':r['culture_type'],'topic_label':labels[r['culture_type']],'research_label':labels[r['culture_type']],'human_direction':'unresolved','ai_direction':'unresolved','evidence_complete':False,'edition':r['date'],'summary_basis':'Selected '+fmt(r['date']),'has_editorial':False,'reading_minutes':max(1,round(len(r.get('excerpt','').split())/200))})
    for item in out:
        for field in ('excerpt','quote_context'):
            item[field+'_parts']=[{'text':part[1:-1] if part.startswith('_') and part.endswith('_') else part,'emphasis':part.startswith('_') and part.endswith('_')} for part in re.split(r'(_[^_]+_)',item.get(field,''))]
    return sorted(out,key=lambda x:(x['date'],x['key']),reverse=True)

def advertising_eligible(page, story=None, news=()):
    """Exclude source-only links, account pages and cultural excerpts from ads."""
    def editorial(item):
        return bool(item.get('has_editorial') and (item.get('what_happened') or item.get('body_paragraphs')))
    if page == 'home':
        return len(news) >= 4 and any(editorial(item) for item in news)
    return page == 'story' and bool(story) and story.get('kind') in ('news', 'research') and editorial(story)

def sponsor_is_active(config, day, preview=False):
    sponsor=config.get('sponsor',{})
    return bool(not preview and sponsor.get('enabled') and sponsor.get('starts','')<=day<=sponsor.get('ends',''))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--preview',action='store_true');parser.add_argument('--mock',action='store_true',help='Compatibility alias for the real-source preview');parser.add_argument('--output',default='_site');parser.add_argument('--update-archive',action='store_true');args=parser.parse_args()
    global SITE;SITE=ROOT/args.output
    if SITE.resolve()==ROOT or ROOT not in SITE.resolve().parents:raise ValueError('Build directory must be inside the repo')
    preview=args.preview or args.mock
    config=load_config(ROOT);release,sym=inputs(preview);counts=validate_pair(release,sym)
    if preview:
        registry={};readiness={};editorial=json.loads((ROOT/'data/preview/editorial.json').read_text())
        config.update(community_enabled=False,ga4_measurement_id='',supabase_publishable_key='');config['adsense']['enabled']=False
    else:
        registry,readiness,editorial=dbmaps(False)
        axes_by_id={x['event_id']:x for x in sym['evidence']}
        for seedfile in sorted((ROOT/'data/editorial').glob('seed-*.json')):
            for eid,version in json.loads(seedfile.read_text()).items():
                row=axes_by_id.get(eid)
                if row and version_valid(version,row,release) and not version_valid(editorial.get(eid),row,release):editorial[eid]=version
    news=cards(release,sym,registry,readiness,editorial,preview);research=papers();culture=culture_items()
    archivepath=ROOT/'data/archive/stories.json'
    old=json.loads(archivepath.read_text()).get('stories',[]) if archivepath.exists() else []
    current_keys={x['key'] for x in news}
    allitems={x['key']:x for x in old if not (x.get('kind')=='news' and x.get('edition')==release['release_id'] and x['key'] not in current_keys)}
    for item in news+research+culture:
        previous=allitems.get(item['key'])
        if previous and previous.get('path') and re.fullmatch(r'(story|research|culture)/[a-zA-Z0-9_-]+/index.html',previous['path']):
            item['path']=previous['path'];item['slug']=previous['slug']
        allitems[item['key']]=item
    # Preserve historical links. For a current research item, replace a changed
    # or withheld summary with its current metadata-only record.
    for row in research:
        allitems[row['key']]=row
    allcards=sorted(allitems.values(),key=lambda x:x['date'],reverse=True)
    raw_archive=copy.deepcopy(allcards)
    english=EnglishPublication(ROOT, allow_model=(not preview and os.environ.get('BRIEF_TRANSLATE_ENGLISH')=='true'))
    current_order={x['key']:i for i,x in enumerate(news+research+culture)}
    public_by_key={x['key']:english.apply(x) for x in sorted(allcards,key=lambda x:current_order.get(x['key'],100000))}
    allcards=[public_by_key[x['key']] for x in allcards]
    news=[public_by_key[x['key']] for x in news]
    research=[public_by_key[x['key']] for x in research]
    culture=[public_by_key[x['key']] for x in culture]
    for item in allcards:
        item['content_hash'],_=content_version(item)
    for item in allcards:
        if item.get('image_path') and not (ROOT/item['image_path']).is_file():item['image_path']=''
    weekly_overview,overview_archive=prepare_weekly_overviews(news,research,release,ROOT,write_archive=(args.update_archive and not preview))
    if SITE.exists():shutil.rmtree(SITE)
    SITE.mkdir();shutil.copytree(ROOT/'assets',SITE/'assets',ignore=shutil.ignore_patterns('placeholder.txt'))
    shutil.copyfile(ROOT/'assets/favicon.ico', SITE/'favicon.ico')
    env=Environment(loader=FileSystemLoader(str(ROOT/'templates')),autoescape=select_autoescape(['html']))
    baseurl=config.get('site_url','').rstrip('/')
    if not baseurl and os.environ.get('GITHUB_REPOSITORY'):
        owner,repo=os.environ['GITHUB_REPOSITORY'].split('/',1);baseurl=f'https://{owner}.github.io/{repo}'
    public_config={k:config.get(k) for k in ('site_name','supabase_url','supabase_publishable_key','community_enabled','ga4_measurement_id','adsense')}
    public_config['site_url']=baseurl;public_config['is_preview']=preview
    public_config['layout_version']=LAYOUT;public_config['release_id']=release['release_id']
    public_config['notifications']=public_settings(config, preview)
    sponsor=config.get('sponsor',{})
    today=reading_day().isoformat()
    sponsor_active=sponsor_is_active(config,today,preview)
    market_counts={code:sum(code in c['markets'] for c in news) for code,_ in MARKETS}
    rotation=rotation_plan(news, release['release_id'], release['period_end'])
    day_layout=rotation['layouts'][rotation['slot']]
    bykey={c['key']:c for c in news}
    lead=bykey.get(day_layout['lead'])
    highlights=[bykey[k] for k in day_layout['highlights']]
    news=[bykey[k] for k in day_layout['order']]
    for rank, item in enumerate(news):item['daily_rank']=rank
    defaults={'config':config,'release':release,'period_label':fmt(release['period_start'])+' - '+fmt(release['period_end']),'markets':MARKETS,'topics':list(TOPICS.items()),'market_counts':market_counts,'news_count':len(news),'generated_at':utc_now(),'is_preview':preview,'public_config':public_config,'sponsor_active':sponsor_active,'counts':counts}
    latest_culture_date=max((x['date'] for x in culture),default='')
    defaults.update(rotation=rotation, reading_date=fmt(rotation['selection_date']))
    defaults.update(culture_latest=[x for x in culture if x['date']==latest_culture_date],culture_date=fmt(latest_culture_date))
    culture_featured=sorted(defaults['culture_latest'],key=lambda x:({'illustration':0,'poetry':1,'music':2,'text':3,'quote':4}.get(x['culture_type'],5)))
    defaults.update(culture_featured=culture_featured, research_featured=sorted(research,key=lambda x:not x.get('has_editorial'))[:6])
    defaults.update(culture_discoveries=[english.apply(x) for x in culture_discoveries(root=ROOT)],culture_library=culture_summary(ROOT))
    defaults.update(weekly_overview=weekly_overview,overview_archive=overview_archive)
    def render(path,template,**ctx):
        target=SITE/path;target.parent.mkdir(parents=True,exist_ok=True)
        prefix='../'*len(Path(path).parent.parts)
        local=lambda value:prefix+value
        # Full text stays in HTML. The interaction payload only needs metadata.
        local_items=allcards if ctx.get('page') in ('saved','archive','digest') else (
            [ctx['story']]+ctx.get('related',[]) if ctx.get('story') else
            news+defaults['culture_latest']+defaults['research_featured'] if ctx.get('page')=='home' else ctx.get('items',[]))
        client=[{k:x.get(k) for k in ('key','headline','path','kind','date','topic','markets','publisher','deck','daily_rank','display_date','topic_label','market_label','reading_minutes','creator','creator_origin','content_hash','edition')} for x in local_items]
        page_defaults={**defaults, 'ads_eligible':advertising_eligible(ctx.get('page'),ctx.get('story'),news)}
        page_defaults['public_config']={**public_config,'adsense':{**public_config['adsense'],'page_eligible':page_defaults['ads_eligible']}}
        output=env.get_template(template).render(**page_defaults,local=local,canonical=(baseurl+'/'+path.removesuffix('index.html') if baseurl else ''),client_items=client,**ctx)
        target.write_text(output,encoding='utf-8')
    render('index.html','index.html',page='home',lead=lead,highlights=highlights,feed=news)
    render('research/index.html','collection.html',page='research',items=research)
    render('culture/index.html','culture.html',page='culture',items=culture)
    render('saved/index.html','collection.html',page='saved',items=allcards)
    render('archive/index.html','collection.html',page='archive',items=allcards)
    render('notifications/index.html','notifications.html',page='notifications')
    render('notifications/read/index.html','digest.html',page='digest')
    render('support/index.html','support.html',page='support')
    weekly_image=(baseurl+'/'+weekly_overview['markets']['image_path']) if baseurl else weekly_overview['markets']['image_path']
    weekly_schema={'@context':'https://schema.org','@type':'Article','headline':weekly_overview['markets']['title'],'description':weekly_overview['markets']['deck'],'datePublished':weekly_overview['period_end'],'dateModified':weekly_overview['period_end'],'author':{'@type':'Organization','name':'AI Empowerment Observatory'},'publisher':{'@type':'Organization','name':'The Brief'},'image':[weekly_image] if weekly_image else []}
    render('week-from-above/index.html','weekly-archive.html',page='weekly-archive',overview_archive=overview_archive,page_image=weekly_overview['markets']['image_path'],structured_data={'@context':'https://schema.org','@type':'CollectionPage','name':'Weekly AI overviews','description':'One-minute weekly views across five AI discovery markets and research.'})
    render(weekly_overview['path'],'weekly-overview.html',page='weekly-overview',weekly_overview=weekly_overview,page_image=weekly_overview['markets']['image_path'],structured_data=weekly_schema)
    for page in ('about','privacy','account','moderation'):
        render(f'{page}/index.html','pages.html',page=page)
    for item in allcards:
        related=[c for c in allcards if c['key']!=item['key'] and c['topic']==item['topic']][:3]
        render(item['path'],'culture-story.html' if item['kind']=='culture' else 'story.html',page='story',story=item,related=related)
    data=SITE/'data';data.mkdir()
    payload={'schema_version':'aieo_brief_public_v3','release_id':release['release_id'],'period_start':release['period_start'],'period_end':release['period_end'],'generated_at':utc_now(),'story_count':len(news),'research_count':len(research),'source_release_sha256':release['content_sha256'],'directional_counts':counts,'stories':news,'research':research}
    payload['complete_content']=release.get('complete_content',{})
    payload['daily_selection']=rotation
    payload.update(culture_count=len(culture),culture=culture)
    payload['source_relationship_sha256'] = relationship_fingerprint(sym)
    payload['weekly_overview']=weekly_overview
    (data/'current.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
    (data/'public-items.json').write_text(json.dumps({'items':allcards},ensure_ascii=False)+'\n')
    social=data/'social';social.mkdir()
    (social/'current.json').write_text(json.dumps(social_queue(weekly_overview,baseurl),ensure_ascii=False,indent=2)+'\n')
    shutil.copyfile(ROOT/'assets/news-worker.js', SITE/'news-worker.js')
    (SITE/'manifest.webmanifest').write_text(json.dumps({'name':'The Brief — AI news','short_name':'The Brief',
        'id':'./','start_url':'./','scope':'./','display':'standalone','background_color':'#ffffff',
        'theme_color':'#122b3d','icons':[
            {'src':'assets/favicon-192.png','sizes':'192x192','type':'image/png','purpose':'any'},
            {'src':'assets/favicon-512.png','sizes':'512x512','type':'image/png','purpose':'any'}]})+'\n')
    (SITE/'.nojekyll').touch()
    publisher_id=(config.get('adsense') or {}).get('publisher_id','')
    if re.fullmatch(r'ca-pub-\d{16}',publisher_id) and not preview:
        (SITE/'ads.txt').write_text('google.com, '+publisher_id.removeprefix('ca-')+', DIRECT, f08c47fec0942fa0\n')
    if baseurl and not preview and not urlparse(baseurl).hostname.endswith('.github.io') and not urlparse(baseurl).path.strip('/'):
        (SITE/'CNAME').write_text(urlparse(baseurl).hostname+'\n')
    if baseurl:
        rss=['<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>AIEO Brief</title><link>'+xml_escape(baseurl)+'</link><description>Clear AI news and research, with original sources.</description>']
        weekly_url=baseurl+'/'+weekly_overview['path'].removesuffix('index.html')
        rss.append('<item><title>'+xml_escape(weekly_overview['markets']['title'])+'</title><link>'+xml_escape(weekly_url)+'</link><guid isPermaLink="false">weekly:'+xml_escape(weekly_overview['release_id'])+'</guid><description>'+xml_escape(weekly_overview['markets']['deck'])+'</description></item>')
        for item in sorted(news+research+culture,key=lambda x:x['date'],reverse=True)[:100]:
            url=baseurl+'/'+item['path'].removesuffix('index.html');rss.append('<item><title>'+xml_escape(item['headline'])+'</title><link>'+xml_escape(url)+'</link><guid isPermaLink="false">'+xml_escape(item['key'])+'</guid><description>'+xml_escape(item['deck'])+'</description></item>')
        (SITE/'feed.xml').write_text(''.join(rss)+'</channel></rss>')
        locations=['index.html','research/index.html','culture/index.html','about/index.html','week-from-above/index.html']+[x['path'] for x in overview_archive]+[i['path'] for i in allcards]
        (SITE/'sitemap.xml').write_text('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+''.join('<url><loc>'+xml_escape(baseurl+'/'+p.removesuffix('index.html'))+'</loc></url>' for p in locations)+'</urlset>')
    else:(SITE/'feed.xml').write_text('<?xml version="1.0"?><rss version="2.0"><channel><title>AIEO Brief preview</title><link>https://observatory.hamelberg-ai.com</link><description>Set the Brief site URL for its live feed.</description></channel></rss>')
    (SITE/'robots.txt').write_text('User-agent: *\n'+('Disallow: /\n' if preview else 'Allow: /\n'+('Sitemap: '+baseurl+'/sitemap.xml\n' if baseurl else '')))
    if args.update_archive and not preview:
        archivepath.parent.mkdir(parents=True,exist_ok=True);archivepath.write_text(json.dumps({'schema_version':'aieo_brief_archive_v1','stories':raw_archive},ensure_ascii=False,indent=2)+'\n')
    summary={'release':release['release_id'],'news':len(news),'editorial_summaries':sum(x['has_editorial'] for x in news),'research':len(research),'historical_pages':len(allcards),'community_connected':bool(config.get('community_enabled')),'preview':preview}
    summary['culture']=len(culture)
    summary['weekly_overview_path']=weekly_overview['path']
    summary['weekly_market_word_count']=weekly_overview['markets']['word_count']
    summary['weekly_research_word_count']=weekly_overview['research']['word_count']
    summary['english_publication']={**english.summary(),'scope':'current items, archived items and discovery credits','current_news_pending':sum(x.get('english_status')=='pending' for x in news),'current_research_pending':sum(x.get('english_status')=='pending' for x in research),'current_culture_pending':sum(x.get('english_status')=='pending' for x in culture)}
    if english.pending:print('::warning::Some English display translations remain pending. Inspect current and archive coverage in the build summary before treating the edition as fully translated.')
    print(json.dumps(summary,indent=2))
    Path(ROOT/'build-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    return 0
if __name__=='__main__':raise SystemExit(main())
