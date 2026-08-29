#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, os, re, shutil
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
import requests
from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT=Path(__file__).resolve().parents[1]; SITE=ROOT/'_site'; OBS=os.environ.get('OBSERVATORY_BASE_URL','https://observatory.hamelberg-ai.com').rstrip('/')
REL={
'mutualism':('People ↑','AI ↑','Both gain','Mutualism','mutualism'),
'ai_benefiting_parasitism':('People ↓','AI ↑','AI side gains, people are constrained','AI-benefiting parasitism','ai-benefit'),
'human_benefiting_parasitism':('People ↑','AI ↓','People gain, AI side is constrained','Human-benefiting parasitism','human-benefit'),
'competition':('People ↓','AI ↓','Both are constrained','Competition or co-constraint','competition'),
'human_enabling_only':('People ↑','AI ?','People-side gain only','One-sided human signal','human-only'),
'human_constraining_only':('People ↓','AI ?','People-side constraint only','One-sided human signal','human-only'),
'ai_enabling_only':('People ?','AI ↑','AI-side gain only','One-sided AI signal','ai-only'),
'ai_constraining_only':('People ?','AI ↓','AI-side constraint only','One-sided AI signal','ai-only'),
'insufficient_evidence':('People ?','AI ?','Evidence is still limited','Insufficient evidence','insufficient')}

def fetch(url):
 r=requests.get(url,timeout=30); r.raise_for_status(); return r.json()
def slugify(v): return (re.sub(r'[^a-z0-9]+','-',str(v or '').casefold()).strip('-')[:76] or 'development')
def safe_url(v):
 try:
  p=urlparse(str(v or '')); return str(v) if p.scheme in {'http','https'} else '#'
 except Exception:return '#'
def fmt(v):
 try:return datetime.strptime(str(v or '')[:10],'%Y-%m-%d').strftime('%-d %b %Y')
 except Exception:return str(v or '')[:10] or 'Date unavailable'
def relmeta(row):
 key=str((row or {}).get('configuration') or 'insufficient_evidence'); a,b,c,d,e=REL.get(key,REL['insufficient_evidence']); return {'configuration':key,'people':a,'ai':b,'label':c,'technical':d,'class':e,'reviewed':bool((row or {}).get('reviewed'))}
def novelty(e):
 v=str(e.get('novelty_status') or '')
 if v=='recurring' or e.get('recurring_in_period'):return 'Seen before'
 if v=='first_time' or e.get('first_time_in_period'):return 'New to AIEO'
 if v=='follow_on_development' or e.get('follow_on_development'):return 'New follow-on'
 return 'Novelty under review'
def human_copy(v): return {'enabling':'People gain capability, access, control, or participation.','constraining':'People face reduced capability, access, control, or participation.','neutral':'No directional human effect is established.'}.get(v,'The human-side effect is not established.')
def ai_copy(v): return {'enabling':'The AI or operator side gains capability, data, reach, resources, or operating freedom.','constraining':'The AI or operator side loses capability, reach, resources, or operating freedom.','neutral':'No directional AI-side effect is established.'}.get(v,'The AI-side effect is not established.')

def dbmaps(mock):
 if mock:
  return tuple(json.loads((ROOT/'data/mock'/f).read_text()) for f in ['stories.json','readiness.json'])
 from supabase import create_client
 c=create_client(os.environ['SUPABASE_URL'],os.environ['SUPABASE_SECRET_KEY']); stories={}; readiness={}
 for start in range(0,2000,500):
  rows=c.table('brief_stories').select('story_id,event_id,slug,status').range(start,start+499).execute().data or []
  for r in rows:
   if r.get('event_id'):stories[str(r['event_id'])]=r
  if len(rows)<500:break
 for start in range(0,2000,500):
  rows=c.table('brief_event_evidence_readiness').select('event_id,source_count,full_source_count,headline_only_count,editorial_evidence_level').range(start,start+499).execute().data or []
  for r in rows:readiness[str(r['event_id'])]=r
  if len(rows)<500:break
 return stories,readiness

def inputs(mock):
 if mock:return json.loads((ROOT/'data/mock/release.json').read_text()),json.loads((ROOT/'data/mock/symbiosis.json').read_text())
 return fetch(f'{OBS}/data/releases/current.json'),fetch(f'{OBS}/data/symbiosis/current.json')

def cards(release,sym,stories,readiness):
 rm={str(r.get('event_id')):r for r in sym.get('evidence',[]) if r.get('event_id')}; out=[]
 for e in release.get('evidence',[]):
  eid=str(e.get('effective_event_id') or e.get('event_id') or '')
  if not eid:continue
  reg=stories.get(eid,{}) ; rd=readiness.get(eid,{}) ; level=str(rd.get('editorial_evidence_level') or 'headline_only'); rr=rm.get(eid,{}) ; rel=relmeta(rr)
  title=str(e.get('event_title') or 'Untitled AI development').strip(); summary=str(e.get('event_summary') or '').strip()
  headline=('Early signal: '+title) if level=='headline_only' else title
  happened=summary or ('AIEO detected this development, but retained source evidence is still limited. Open the source links below.' if level=='headline_only' else 'AIEO grouped the supporting coverage into one development. Open the source links below.')
  why=(str(rr.get('reasoning') or '').strip() if level!='headline_only' else '') or ('AIEO is keeping the interpretation conservative until stronger source evidence is available.' if level=='headline_only' else 'The relationship lens separates what changes for people from what changes for the AI or operator side.')
  src=[{'publisher':s.get('publisher') or s.get('name') or 'Publication','headline':s.get('headline') or 'Open source','url':safe_url(s.get('url')),'published_date':s.get('published_date') or ''} for s in (e.get('sources') or [])]
  slug=reg.get('slug') or f'{slugify(title)}-{eid.replace("-","")[:8]}'
  out.append({'event_id':eid,'story_id':reg.get('story_id'),'slug':slug,'url':f'/story/{slug}/','headline':headline,'what_happened':happened,'why_it_matters':why,'event_date':fmt(e.get('event_date')),'event_date_raw':str(e.get('event_date') or ''),'source_count':int(rd.get('source_count') or len(src)),'full_source_count':int(rd.get('full_source_count') or 0),'evidence_level':level,'novelty':novelty(e),'sources':src,'relationship':rel,'human_copy':human_copy(str(rr.get('human_direction') or 'unclear')),'ai_copy':ai_copy(str(rr.get('ai_direction') or 'unclear'))})
 order={'strong_multi_source':0,'mixed_with_full_source':1,'single_full_source':2,'snippet_or_excerpt_only':3,'headline_only':4}; out.sort(key=lambda x:(order.get(x['evidence_level'],9),-x['source_count'],x['event_date_raw'])); return out

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--mock',action='store_true');a=ap.parse_args(); release,sym=inputs(a.mock); sm,rd=dbmaps(a.mock); cs=cards(release,sym,sm,rd)
 if not cs:raise SystemExit('No current stories could be built')
 if SITE.exists():shutil.rmtree(SITE)
 SITE.mkdir();shutil.copytree(ROOT/'assets',SITE/'assets')
 env=Environment(loader=FileSystemLoader(str(ROOT/'templates')),autoescape=select_autoescape(['html']))
 complete=int((sym.get('event') or {}).get('complete_configuration_count') or 0); cc=(sym.get('event') or {}).get('configuration_counts') or {}; ticker=[]
 for k in ['mutualism','ai_benefiting_parasitism','human_benefiting_parasitism','competition']:
  m=relmeta({'configuration':k,'reviewed':True});m['key']=k;m['count']=int(cc.get(k) or 0);m['share']=round(m['count']/complete*100) if complete else 0;ticker.append(m)
 lead=next((c for c in cs if c['evidence_level']!='headline_only'),cs[0]); rest=[c for c in cs if c['event_id']!=lead['event_id']]; by={}
 for c in cs:by.setdefault(c['relationship']['configuration'],[]).append(c)
 ctx={'release':release,'symbiosis':sym,'cards':cs,'lead':lead,'main_cards':rest,'ticker':ticker,'by_relationship':by}
 (SITE/'index.html').write_text(env.get_template('index.html').render(**ctx),encoding='utf-8')
 t=env.get_template('story.html')
 for c in cs:
  p=SITE/'story'/c['slug'];p.mkdir(parents=True);(p/'index.html').write_text(t.render(story=c,release=release),encoding='utf-8')
 d=SITE/'data';d.mkdir();(d/'current.json').write_text(json.dumps({'release_id':release.get('release_id'),'story_count':len(cs),'stories':[{'event_id':c['event_id'],'slug':c['slug'],'headline':c['headline'],'relationship':c['relationship'],'evidence_level':c['evidence_level'],'source_count':c['source_count'],'full_source_count':c['full_source_count']} for c in cs]},indent=2)+'\n')
 print(json.dumps({'release_id':release.get('release_id'),'stories_built':len(cs),'with_full_source':sum(c['full_source_count']>0 for c in cs),'headline_only':sum(c['evidence_level']=='headline_only' for c in cs)},indent=2))
if __name__=='__main__':raise SystemExit(main())
