#!/usr/bin/env python3
"""Resumable editorial writing; each successful version is saved independently.
No complete body, no invented rewrite. Existing publisher-linked entries stay readable.
"""
from __future__ import annotations
import argparse,json,os,time,uuid
import ai_runtime
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
from supabase import create_client
from brief_contract import PROMPT_VERSION,digest,fixed_relationship,validate_pair
from brief_database import current_maps
from build_site import inputs
from editorial_engine import write_story,failure_diagnostic,ENGINE_VERSION
from source_evidence_quality import assess_body
ROOT=Path(__file__).resolve().parents[1]
MODEL=ai_runtime.identity()['model'] if ai_runtime.uses_openai() else os.environ.get('BRIEF_EDITORIAL_MODEL','Qwen3-4B-Q4_K_M')
MODEL_REVISION=ai_runtime.identity()['revision'] if ai_runtime.uses_openai() else os.environ.get('BRIEF_EDITORIAL_MODEL_REVISION','2f3b082b1356a6123f7ed71e65aea340da25d53c')

def source_payload(rows, allowed=None, fingerprints=None):
    result=[]
    for row in sorted(rows,key=lambda r:(not r.get('is_canonical_source'),str(r.get('article_id')))):
        aid=str(row.get('article_id') or '')
        if allowed is not None and aid not in allowed:continue
        evidence=str(row.get('evidence_text') or '').strip()
        quality=assess_body({'body_text':evidence,'content_basis':row.get('evidence_basis')})
        if row.get('evidence_basis')!='full_source' or not quality['usable_complete_body']:continue
        if fingerprints is not None and fingerprints.get(aid)!=quality.get('body_sha256'):continue
        result.append({'source_number':len(result)+1,'publisher':str(row.get('publisher') or ''),'headline':str(row.get('source_headline') or ''),'published_at':str(row.get('published_at') or ''),'evidence_basis':'full_source','evidence':evidence,'evidence_ref':row.get('evidence_ref'),'source_url':row.get('source_url'),'quality':quality})
    return result

def fingerprint(event,axes,sources):
    return digest({'prompt_version':PROMPT_VERSION,'model_revision':MODEL_REVISION,'event_id':event.get('effective_event_id') or event.get('event_id'),'title':event.get('event_title'),'axes':axes,'sources':[{'publisher':s['publisher'],'headline':s['headline'],'hash':digest(s['evidence'])} for s in sources]})
def same_input(latest,fp):return ((latest or {}).get('evidence_basis_summary') or {}).get('input_fingerprint')==fp

def candidates(release,sym,maps,force=False):
    stories,readiness,evidence,versions=maps;axis={r['event_id']:r for r in sym['evidence']};selected=[]
    counts={'unchanged':0,'source_not_ready':0,'new_registry':0,'needs_model':0,'needs_rebind':0}
    for event in sorted(release['evidence'],key=lambda e:(str(e.get('event_date')),str(e.get('event_id'))),reverse=True):
        eid=str(event.get('effective_event_id') or event['event_id']);relation=fixed_relationship(axis[eid]);story=stories.get(eid)
        bound=bool(release.get('complete_content'))
        allowed={str(s['article_id']) for s in event.get('sources',[])} if bound else None
        fingerprints=(axis[eid].get('evidence_basis_summary') or {}).get('source_fingerprints',{}) if bound else None
        sources=source_payload(evidence.get(eid,[]),allowed,fingerprints)
        if not sources or not relation['axes'].get('evidence_complete'):counts['source_not_ready']+=1;continue
        fp=fingerprint(event,relation['axes'],sources);latest=versions.get(str((story or {}).get('story_id')))
        reusable=not force and same_input(latest,fp) and latest.get('publication_status') in ('published','preview')
        if reusable and latest['evidence_basis_summary'].get('source_release_sha256')==release['content_sha256']:
            counts['unchanged']+=1;continue
        key='needs_rebind' if reusable else 'needs_model';counts[key]+=1
        if not story:counts['new_registry']+=1
        selected.append({'event':event,'eid':eid,'relation':relation,'sources':sources,'fp':fp,'latest':latest,'story':story,'reuse':reusable})
    # A failed item from an earlier attempt does not starve the rest of the week.
    q=ROOT/'data/editorial/retry-state.json';state=json.loads(q.read_text()) if q.exists() else {}
    selected.sort(key=lambda x:(state.get(x['fp'],{}).get('attempts',0),not x['reuse']))
    return selected,counts,state

def valid_uuid(v):
    try:return str(uuid.UUID(str(v)))
    except (ValueError,TypeError):return None

def persist(client,item,release,draft,proof):
    story=item['story'];eid=item['eid'];latest=item['latest'];relation=item['relation']
    if not story:
        story={'story_id':str(uuid.uuid4()),'event_id':eid,'slug':'development-'+eid,'status':'active'}
        # The existing registry schema may use a different status vocabulary;
        # its database default is authoritative.
        story.pop('status')
        rows=client.table('brief_stories').insert(story).execute().data or []
        if not rows:raise RuntimeError('Story registry did not return the saved row.')
        story=rows[0]
    basis={'prompt_version':PROMPT_VERSION,'source_release_sha256':release['content_sha256'],'release_id':release['release_id'],'axes_sha256':digest(relation['axes']),'axes':relation['axes'],'input_fingerprint':item['fp'],'full_source_count':len(item['sources']),'model':MODEL,'claim_status':draft.get('claim_status','reporting'),'limitation':draft.get('limitation',''),'validation':'source_support_and_original_wording'}
    if item['reuse']:
        basis['claim_status']=latest['evidence_basis_summary'].get('claim_status','reporting');basis['limitation']=latest['evidence_basis_summary'].get('limitation','')
        generated_id=latest.get('generated_artifact_id');basis={**latest['evidence_basis_summary'],**basis}
    else:
        output={k:v for k,v in draft.items() if k!='support'}
        artifact={'entity_type':'brief_story','entity_id':str(story['story_id']),'task':'editorial_story','run_id':os.environ.get('GITHUB_RUN_ID'),'provider':'openai' if ai_runtime.uses_openai() else 'local_llama_cpp','model_name':MODEL,'model_revision':MODEL_REVISION,'prompt_version':PROMPT_VERSION,'classifier_version':'independent-directional-v1','input_sha256':item['fp'],'output_sha256':digest(output),'output_text':json.dumps(output,ensure_ascii=False),'output_json':output,'evidence_snapshot_ids':[ref for s in item['sources'] if (ref:=valid_uuid(s.get('evidence_ref')))],'human_review_status':'governed_preview'}
        client.table('brief_editorial_provenance').upsert({'input_sha256':item['fp'],'proof':proof},on_conflict='input_sha256').execute()
        rows=client.table('brief_generated_artifacts').insert(artifact).execute().data or []
        if not rows:raise RuntimeError('Draft provenance was not saved.')
        generated_id=rows[0]['generated_id']
    version={k:draft.get(k,'') for k in ('editorial_headline','editorial_deck','what_happened','why_it_matters','for_humans','for_ai')}
    version.update(story_id=story['story_id'],event_id=eid,version_number=int((latest or {}).get('version_number') or 0)+1,body_markdown=draft.get('body_markdown') or '\n\n'.join(draft['body_paragraphs']),relationship_configuration=relation['configuration'],human_direction=relation['human_direction'],ai_direction=relation['ai_direction'],evidence_basis_summary=basis,generated_artifact_id=generated_id,review_status='model_generated_governed',publication_status='preview',supersedes_story_version_id=(latest or {}).get('story_version_id'))
    client.table('brief_story_versions').insert(version).execute()
    client.table('brief_stories').update({'current_headline':draft['editorial_headline'],'current_deck':draft['editorial_deck'],'current_takeaway':draft['why_it_matters'],'last_updated_at':datetime.now(timezone.utc).isoformat()}).eq('story_id',story['story_id']).execute()

def main():
    p=argparse.ArgumentParser();p.add_argument('--limit',type=int,default=0);p.add_argument('--force',action='store_true');p.add_argument('--dry-run',action='store_true');p.add_argument('--max-runtime-minutes',type=int,default=45);p.add_argument('--strict',action='store_true');args=p.parse_args()
    if not 1<=args.max_runtime_minutes<=105 or not 0<=args.limit<=1000:raise ValueError('Use a 1–105 minute budget and a limit of 0–1000.')
    release,sym=inputs();validate_pair(release,sym)
    print('Reading completed Observatory edition: '+release['release_id'],flush=True)
    client=create_client(os.environ['SUPABASE_URL'],os.environ['SUPABASE_SECRET_KEY'])
    client.table('brief_editorial_provenance').select('input_sha256').limit(1).execute()
    ids=[str(e.get('effective_event_id') or e['event_id']) for e in release['evidence']]
    items,counts,state=candidates(release,sym,current_maps(client,ids),args.force)
    if args.limit:items=items[:args.limit]
    counts.update(selected=len(items),generated=0,rebound=0,failed=0,deferred=0)
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'],'a') as f:f.write(f'needs_model={str(any(not x["reuse"] for x in items)).lower()}\npending={len(items)}\n')
    if args.dry_run:print(json.dumps(counts,indent=2));return 0
    ai_runtime.require_key()
    deadline=time.monotonic()+args.max_runtime_minutes*60;failures=[]
    for n,item in enumerate(items):
        if time.monotonic()>deadline-90:counts['deferred']=len(items)-n;break
        stage='generation'
        print(f'[{n+1}/{len(items)}] Preparing news {item["eid"]}',flush=True)
        try:
            if item['reuse']:draft=item['latest'];proof={}
            else:draft,proof=write_story(item['event'],item['relation']['axes'],item['sources'],deadline=deadline)
            stage='persistence'
            persist(client,item,release,draft,proof);counts['rebound' if item['reuse'] else 'generated']+=1;state.pop(item['fp'],None)
            print(f'Saved {item["eid"]}: {draft["editorial_headline"]}',flush=True)
        except TimeoutError:counts['deferred']=len(items)-n;break
        except Exception as e:
            counts['failed']+=1;state[item['fp']]={'attempts':state.get(item['fp'],{}).get('attempts',0)+1,'last_attempt':datetime.now(timezone.utc).isoformat()}
            diagnostic=failure_diagnostic(e,stage)
            failures.append({'event_id':item['eid'],**diagnostic})
            # Do not print PostgREST errors: they can contain private failing rows.
            print(f'Kept source link for {item["eid"]}; draft withheld: '+json.dumps(diagnostic,sort_keys=True),flush=True)
    path=ROOT/'data/editorial';path.mkdir(parents=True,exist_ok=True)
    # Keep bounded retry metadata only; no bodies, quotes or private errors enter Git.
    active={x['fp'] for x in items};state={k:v for k,v in state.items() if k in active}
    (path/'retry-state.json').write_text(json.dumps(state,indent=2)+'\n')
    failure_counts=dict(Counter(x['code'] for x in failures))
    (path/'status.json').write_text(json.dumps({'release_id':release['release_id'],'engine_version':ENGINE_VERSION,'counts':counts,'failure_counts':failure_counts,'failed_items':failures,'updated_at':datetime.now(timezone.utc).isoformat()},indent=2)+'\n')
    print(json.dumps(counts,indent=2))
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as f:
            f.write('## Brief news generation\n\nCompleted edition: **'+release['release_id']+'**.\n\n'+ '\n'.join(f'- {k.replace("_"," ")}: **{v}**' for k,v in counts.items())+'\n\nDeferred items remain queued for the next generation run. Source links remain available.\n')
            if failures:f.write('\nDraft rejection reasons:\n\n'+'\n'.join(f'- `{code}`: **{count}**' for code,count in sorted(failure_counts.items()))+'\n\nSafe per-item details are in `data/editorial/status.json`.\n')
    if counts['failed'] and (args.strict or not counts['generated']+counts['rebound']):return 1
    return 0
if __name__=='__main__':raise SystemExit(main())
