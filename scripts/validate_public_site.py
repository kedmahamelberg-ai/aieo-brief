#!/usr/bin/env python3
"""Static publication gate: source counts, destinations and private-data exclusion."""
import argparse,collections,json,re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit,unquote
ROOT=Path(__file__).resolve().parents[1]
PRIVATE_KEYS={'evidence_text','body_text','private_validation','segment_readings','support','evidence_basis_summary','supabase_secret_key','text_sha256','snapshot_id','evidence_ref','private_key','manage_token_hash','subscription_id','auth_key'}
class Page(HTMLParser):
 def __init__(self):super().__init__(convert_charrefs=True);self.links=[];self.ids=[];self.headings=0;self.script_data=[];self.capture=False
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if 'id' in a:self.ids.append(a['id'])
  if tag=='h1':self.headings+=1
  if tag in ('a','link','script','img'):
   value=a.get('src') if tag in ('script','img') else a.get('href')
   if value:self.links.append(value)
  self.capture=tag=='script' and a.get('type')=='application/json'
 def handle_endtag(self,tag):
  if tag=='script':self.capture=False
 def handle_data(self,data):
  if self.capture:self.script_data.append(data)
def inspect_json(value):
 if isinstance(value,dict):
  for k,v in value.items():
   if k.lower() in PRIVATE_KEYS:raise ValueError('Private field leaked: '+k)
   inspect_json(v)
 elif isinstance(value,list):
  for v in value:inspect_json(v)
def validate(site):
 if not site.exists():raise ValueError('No built website')
 payload=json.loads((site/'data/current.json').read_text());inspect_json(payload)
 news=payload['stories'];papers=payload['research'];culture=payload.get('culture',[]);keys=[x['key'] for x in news+papers+culture]
 if len(keys)!=len(set(keys)):raise ValueError('Duplicate story IDs')
 if len(news)!=payload['story_count'] or len(papers)!=payload['research_count']:raise ValueError('Inconsistent collection count')
 if len(culture)!=payload.get('culture_count',0):raise ValueError('Inconsistent culture count')
 for axis in ('human','ai'):
  counts=collections.Counter(x[axis+'_direction'] for x in news)
  if any(counts[k]!=v for k,v in payload['directional_counts'][axis].items()):raise ValueError('Wrong '+axis+' totals')
 for item in news+papers+culture:
  if not item['sources'] or len(item['sources'])!=item['source_count']:raise ValueError('Missing or inconsistent source list')
  if not (site/item['path']).is_file():raise ValueError('Story page missing')
  if item['kind']=='research' and item['has_editorial'] and (not item['limitation'] or item.get('evidence_scope')!='abstract'):raise ValueError('Research summary lacks evidence scope and limit')
  if item['kind']=='culture':
   if not item.get('creator') or not item.get('creator_origin') or not item.get('rights',{}).get('url') or not item.get('work_date'):raise ValueError('Culture attribution missing')
   if item['date']!=item['selected_on']:raise ValueError('Selection date changed')
   if item['culture_type']=='quote' and item['excerpt'] not in item.get('quote_context',''):raise ValueError('Quotation is not in its source context')
   if item['culture_type']=='poetry' and item['excerpt']!='\n'.join(item['poem_lines']):raise ValueError('Poem text was altered')
   if item['culture_type']=='music':
    rights=item['rights'];label=rights.get('label','')
    if not item.get('media_url','').startswith('https://') or not rights['url'].startswith('https://'):raise ValueError('Music lacks a safe source')
    if not label.startswith(('CC BY ','CC BY-SA ','CC0','Public domain')) or re.search(r'\b(?:NC|ND)\b',label):raise ValueError('Music lacks compatible source-declared terms')
 pages=list(site.rglob('*.html'));links=0
 for path in pages:
  raw=path.read_text();parser=Page();parser.feed(raw)
  if parser.headings!=1:raise ValueError(f'{path.relative_to(site)} needs one page heading')
  if len(parser.ids)!=len(set(parser.ids)):raise ValueError('Duplicate element IDs: '+str(path))
  if re.search(r'sb_secret_|SUPABASE_SECRET_KEY|\bservice_role\b|"body_text"|"evidence_text"',raw):raise ValueError('Private material reached HTML')
  for data in parser.script_data:inspect_json(json.loads(data))
  for url in parser.links:
   p=urlsplit(url)
   if p.scheme in ('http','https','mailto'):continue
   if p.scheme or p.netloc:raise ValueError('Unsafe link scheme')
   target=(path.parent/unquote(p.path)).resolve() if p.path else path
   if target.is_dir():target=target/'index.html'
   if site.resolve() not in target.parents or not target.is_file():raise ValueError('Broken local link '+str(path.relative_to(site))+': '+url)
   links+=1
 for f in site.rglob('*'):
  if f.is_file() and f.suffix in ('.sql','.py','.env','.csv'):raise ValueError('Private/build-only file in published website')
 return {'html_pages':len(pages),'local_destinations_checked':links,'news':len(news),'research':len(papers),'culture':len(culture),'source_links':sum(x['source_count'] for x in news),'human_counts':payload['directional_counts']['human'],'ai_counts':payload['directional_counts']['ai'],'result':'passed'}
def main():
 p=argparse.ArgumentParser();p.add_argument('--site',default='_site');args=p.parse_args();result=validate(ROOT/args.site)
 (ROOT/'validation-summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
