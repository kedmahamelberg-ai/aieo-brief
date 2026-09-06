#!/usr/bin/env python3
"""Daily discovery over a rolling week through arXiv and Crossref APIs.
Private abstracts stay in data/research/private; only original summaries/references ship.
"""
from __future__ import annotations
import argparse,hashlib,json,os,re,time
from datetime import datetime,timedelta,timezone
from pathlib import Path
from xml.etree import ElementTree as ET
from urllib.parse import quote
import requests
ROOT=Path(__file__).resolve().parents[1]
AI=re.compile(r'artificial intelligence|machine learning|large language model|generative ai|deep learning|\bllms?\b|\bchatgpt\b|\bchatbots?\b|\bai\b',re.I)
N={'a':'http://www.w3.org/2005/Atom','ar':'http://arxiv.org/schemas/atom'}

def plain(v):return re.sub(r'\s+',' ',re.sub('<[^>]+>',' ',str(v or ''))).strip()
def identity(doi,aid):return 'paper:'+hashlib.sha256((doi.lower() if doi else 'arxiv:'+re.sub(r'v\d+$','',aid)).encode()).hexdigest()[:24]
def get(url,params=None):
 for n in range(3):
  r=requests.get(url,params=params,headers={'User-Agent':'AIEO-Brief/3.0 (research metadata; https://observatory.hamelberg-ai.com)'},timeout=45)
  if r.status_code in (429,500,502,503,504) and n<2:time.sleep(3*(n+1));continue
  r.raise_for_status();return r

def arxiv(start,end,limit):
 q=f'(cat:cs.AI OR cat:cs.CL OR cat:cs.CY OR cat:cs.LG) AND submittedDate:[{start.replace("-","")}0000 TO {end.replace("-","")}2359]'
 response=get('https://export.arxiv.org/api/query',{'search_query':q,'start':0,'max_results':min(limit,50),'sortBy':'submittedDate','sortOrder':'descending'})
 doc=ET.fromstring(response.text);out=[]
 for entry in doc.findall('a:entry',N):
  aid=entry.findtext('a:id','',N).split('/abs/')[-1];doi=entry.findtext('ar:doi','',N).lower();title=plain(entry.findtext('a:title','',N));abstract=plain(entry.findtext('a:summary','',N));day=entry.findtext('a:published','',N)[:10]
  if not aid or not start<=day<=end:continue
  authors=[plain(a.findtext('a:name','',N)) for a in entry.findall('a:author',N)]
  journal=plain(entry.findtext('ar:journal_ref','',N))
  out.append({'key':identity(doi,aid),'doi':doi,'arxiv_id':aid,'original_headline':title,'abstract':abstract,'url':'https://arxiv.org/abs/'+aid,'date':day,'authors':authors,'publisher':'arXiv','source':'arxiv','research_label':'arXiv version · journal reference supplied' if journal else 'Preprint','journal_reference':journal,'evidence_scope':'abstract','access':'Open paper','metadata_sha256':hashlib.sha256((title+'\n'+abstract).encode()).hexdigest()})
 return out

def crossref(source,start,end,limit):
 endpoint='journals/1091-6490/works' if source=='pnas' else 'prefixes/10.2139/works'
 params={'filter':f'from-pub-date:{start},until-pub-date:{end}','query':'artificial intelligence machine learning','sort':'published','order':'desc','rows':min(limit*10,100)}
 if os.environ.get('RESEARCH_CONTACT_EMAIL'):params['mailto']=os.environ['RESEARCH_CONTACT_EMAIL']
 data=get('https://api.crossref.org/'+endpoint,params).json();out=[]
 for row in data.get('message',{}).get('items',[]):
  title=plain((row.get('title') or [''])[0]);abstract=plain(row.get('abstract'))
  if not AI.search(title+' '+abstract):continue
  parts=((row.get('published') or row.get('published-online') or row.get('issued') or {}).get('date-parts') or [[]])[0]
  if len(parts)<3:continue
  day='-'.join([str(parts[0]),f'{parts[1]:02d}',f'{parts[2]:02d}'])
  if not start<=day<=end:continue
  doi=str(row.get('DOI') or '').lower()
  if not doi:continue
  # Crossref supplies updates/retractions; those references remain explicit.
  updates=row.get('update-to') or []
  if any(str(u.get('type')).lower()=='retraction' for u in updates):continue
  licenses=[x.get('URL','') for x in row.get('license') or []]
  oa=any('creativecommons.org/licenses/' in u or 'creativecommons.org/publicdomain/' in u for u in licenses)
  authors=[plain((a.get('given','')+' '+a.get('family',''))) for a in row.get('author') or []]
  out.append({'key':identity(doi,''),'doi':doi,'arxiv_id':'','original_headline':title,'abstract':abstract,'url':'https://doi.org/'+quote(doi,safe='/'),'date':day,'authors':authors,'publisher':'PNAS' if source=='pnas' else 'SSRN','source':source,'research_label':'Journal article' if source=='pnas' else 'Working paper / preprint','evidence_scope':'abstract' if abstract else 'metadata_only','access':'Open-license record' if oa else 'Check access at source','license_urls':licenses,'metadata_sha256':hashlib.sha256((title+'\n'+abstract).encode()).hexdigest()})
  if len(out)>=limit:break
 return out

def main():
 p=argparse.ArgumentParser();p.add_argument('--start');p.add_argument('--end');p.add_argument('--limit-per-source',type=int,default=6);args=p.parse_args()
 today=datetime.now(timezone.utc).date()
 end=args.end or today.isoformat();start=args.start or (datetime.fromisoformat(end).date()-timedelta(days=6)).isoformat()
 if datetime.fromisoformat(start).date()>datetime.fromisoformat(end).date():raise ValueError('Research start must precede its end')
 if args.limit_per_source not in range(1,51):raise ValueError('Limit must be 1 to 50')
 rows=[];status=[]
 for source in ['arxiv','pnas','ssrn']:
  try:
   found=arxiv(start,end,args.limit_per_source) if source=='arxiv' else crossref(source,start,end,args.limit_per_source)
   rows.extend(found);status.append({'source':source,'status':'ok','count':len(found)})
  except (requests.RequestException,ValueError,ET.ParseError) as e:status.append({'source':source,'status':'unavailable','error_type':type(e).__name__})
  time.sleep(3) # Respectful spacing, including arXiv's single-connection guidance.
 if all(x['status']=='unavailable' for x in status):raise SystemExit('All research providers unavailable. Prior published research is retained.')
 private=ROOT/'data/research/private';private.mkdir(parents=True,exist_ok=True)
 unique={}
 for r in rows:
  key=r['key'];old=unique.get(key)
  if not old or (r['source']=='pnas' and r.get('abstract')):unique[key]=r
 payload={'schema_version':'aieo_research_inputs_v1','period_start':start,'period_end':end,'providers':status,'papers':list(unique.values())}
 (private/'inputs.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
 (ROOT/'data/research/collection-status.json').write_text(json.dumps({k:v for k,v in payload.items() if k!='papers'},indent=2)+'\n')
 print(json.dumps({'period_start':start,'period_end':end,'papers':len(unique),'providers':status},indent=2))
if __name__=='__main__':main()
