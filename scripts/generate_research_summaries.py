#!/usr/bin/env python3
"""Summarize actual paper abstracts; distinguish preprints and limited evidence.
Only original prose and bibliographic metadata are written to the public research file.
"""
from __future__ import annotations
import argparse,json,os,time
from collections import Counter
from datetime import datetime,timezone,timedelta,date
from pathlib import Path
from brief_contract import PROMPT_VERSION,digest,safe_url
from editorial_engine import write_story,failure_diagnostic,ENGINE_VERSION
ROOT=Path(__file__).resolve().parents[1]
PUBLIC_FIELDS=('key','doi','arxiv_id','original_headline','url','date','authors','publisher','source','research_label','evidence_scope','access','journal_reference','license_urls','metadata_sha256')

def load():
    path=ROOT/'data/research/private/inputs.json'
    if not path.exists():raise ValueError('Collect recent research before generating summaries.')
    data=json.loads(path.read_text());p=ROOT/'data/research/public.json'
    public=json.loads(p.read_text()) if p.exists() else {'papers':[]}
    return data,{r['key']:r for r in public['papers']}

def pending(data,old):
    return [p for p in data['papers'] if p.get('abstract') and not (old.get(p['key'],{}).get('metadata_sha256')==p['metadata_sha256'] and old[p['key']].get('prompt_version')==PROMPT_VERSION and old[p['key']].get('has_editorial'))]

def public_record(p):
    return {k:p.get(k) for k in PUBLIC_FIELDS if k in p}

def merge_recent(old,updates,end,days=28):
    cutoff=(date.fromisoformat(end)-timedelta(days=days-1)).isoformat()
    merged={key:r for key,r in old.items() if cutoff<=r.get('date','')<=end}
    merged.update({r['key']:r for r in updates if cutoff<=r.get('date','')<=end})
    return sorted(merged.values(),key=lambda r:(r['date'],r['key']),reverse=True)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--dry-run',action='store_true');parser.add_argument('--max-runtime-minutes',type=int,default=15);args=parser.parse_args()
    if not 1<=args.max_runtime_minutes<=60:raise ValueError('Use a 1–60 minute research budget.')
    data,old=load();todo=pending(data,old)
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'],'a') as f:f.write(f'pending={len(todo)}\nneeds_model={str(bool(todo)).lower()}\n')
    if args.dry_run:print(json.dumps({'pending':len(todo),'records':len(data['papers'])}));return
    from supabase import create_client
    client=create_client(os.environ['SUPABASE_URL'],os.environ['SUPABASE_SECRET_KEY'])
    deadline=time.monotonic()+args.max_runtime_minutes*60;counts={'generated':0,'failed':0,'metadata_only':0,'deferred':0,'unchanged':0}
    audit=[];selected=[];failures=[]
    retry_path=ROOT/'data/research/retry-state.json'
    retry=json.loads(retry_path.read_text()) if retry_path.exists() else {}
    def checkpoint():
        payload={'schema_version':'aieo_research_public_v1','period_start':data['period_start'],'period_end':data['period_end'],'generated_at':datetime.now(timezone.utc).isoformat(),'papers':merge_recent(old,selected,data['period_end'])}
        path=ROOT/'data/research/public.json';tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n');tmp.replace(path)
        retry_path.write_text(json.dumps(retry,indent=2)+'\n')
    work=sorted(data['papers'],key=lambda p:(retry.get(p['key'],{}).get('attempts',0),p['date'],p['key']))
    for n,p in enumerate(work):
        if not safe_url(p.get('url')):continue
        prior=old.get(p['key'],{})
        if p not in todo and prior.get('metadata_sha256')==p['metadata_sha256'] and prior.get('has_editorial'):
            counts['unchanged']+=1;selected.append(prior);continue
        base={**public_record(p),'has_editorial':False,'headline':p['original_headline'],'deck':'Open the original research record for the paper and its access options.','what_happened':'','why_it_matters':'','body_paragraphs':[],'limitation':'','summary_basis':'Original paper title','reading_minutes':1}
        if not p.get('abstract'):counts['metadata_only']+=1;selected.append(base);checkpoint();continue
        if time.monotonic()>deadline-90:counts['deferred']+=1;selected.append(base);checkpoint();continue
        retry[p['key']]={'attempts':retry.get(p['key'],{}).get('attempts',0)+1,'last_attempt':datetime.now(timezone.utc).isoformat()}
        stage='generation'
        print(f'[{n+1}/{len(work)}] Preparing research '+p['key'],flush=True)
        try:
            sources=[{'source_number':1,'headline':p['original_headline'],'publisher':p['publisher'],'evidence':p['abstract'],'evidence_basis':'abstract_only'}]
            kind='preprint' if p['source'] in ('arxiv','ssrn') else 'abstract'
            draft,proof=write_story({'event_title':p['original_headline']},{},sources,kind=kind,deadline=deadline)
            record={**base,**{k:draft[k] for k in ('what_happened','why_it_matters','body_paragraphs','limitation','claim_status')},'headline':draft['editorial_headline'],'deck':draft['editorial_deck'],'has_editorial':True,'summary_basis':'Summary of the abstract','prompt_version':PROMPT_VERSION,'reading_minutes':max(1,round(len(' '.join(draft['body_paragraphs']).split())/220))}
            stage='persistence'
            client.table('brief_editorial_provenance').upsert({'input_sha256':digest({'paper':p['key'],'metadata':p['metadata_sha256'],'prompt':PROMPT_VERSION}),'proof':{'abstract':p['abstract'],'metadata_sha256':p['metadata_sha256'],'validation':proof}},on_conflict='input_sha256').execute()
            selected.append(record);counts['generated']+=1
            retry.pop(p['key'],None)
            audit.append({'key':p['key'],'metadata_sha256':p['metadata_sha256'],'abstract':p['abstract'],'validation':proof,'output_sha256':digest(record)})
            print('Saved research '+p['key'],flush=True)
        except TimeoutError:counts['deferred']+=1;selected.append(base)
        except Exception as e:
            counts['failed']+=1;selected.append(base)
            diagnostic=failure_diagnostic(e,stage)
            failures.append({'key':p['key'],**diagnostic})
            print('Summary withheld for '+p['key']+': '+json.dumps(diagnostic,sort_keys=True),flush=True)
        checkpoint()
    retry={k:v for k,v in retry.items() if k in {p['key'] for p in data['papers']}}
    checkpoint()
    (ROOT/'data/research/private/validation.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
    failure_counts=dict(Counter(x['code'] for x in failures))
    (ROOT/'data/research/generation-status.json').write_text(json.dumps({**counts,'engine_version':ENGINE_VERSION,'failure_counts':failure_counts,'failed_items':failures,'updated_at':datetime.now(timezone.utc).isoformat()},indent=2)+'\n')
    print(json.dumps(counts,indent=2))
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as f:
            f.write('## Research\n\n'+'\n'.join(f'- {k}: **{v}**' for k,v in counts.items())+'\n\nAbstract-only summaries are labelled. Sources without an abstract remain original-paper links.\n')
            if failures:f.write('\nDraft rejection reasons:\n\n'+'\n'.join(f'- `{code}`: **{count}**' for code,count in sorted(failure_counts.items()))+'\n\nSafe per-item details are in `data/research/generation-status.json`.\n')
    if counts['failed'] and not counts['generated']:raise SystemExit(1)
if __name__=='__main__':main()
