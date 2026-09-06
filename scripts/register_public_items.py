#!/usr/bin/env python3
"""Publish only the story allowlist for community interactions; never source bodies."""
import json,os
from pathlib import Path
from supabase import create_client
from brief_contract import load_config
ROOT=Path(__file__).resolve().parents[1]
def main():
 config=load_config(ROOT)
 if not config.get('community_enabled'): print('Community is disabled; registration skipped.');return
 client=create_client(os.environ['SUPABASE_URL'],os.environ['SUPABASE_SECRET_KEY'])
 base=config.get('site_url')
 if not base:
  owner,repo=os.environ['GITHUB_REPOSITORY'].split('/',1);base=f'https://{owner}.github.io/{repo}'
 archive=ROOT/'data/archive/stories.json'
 if not archive.exists():raise ValueError('Build the site with --update-archive before registering its stories.')
 stories=json.loads(archive.read_text())['stories']
 rows=[{'story_key':s['key'],'headline':s['headline'],'url':base.rstrip('/')+'/'+s['path'].removesuffix('index.html'),'kind':s['kind'],'published_date':s['date']} for s in stories]
 for start in range(0,len(rows),100):client.table('brief_community_items').upsert(rows[start:start+100],on_conflict='story_key').execute()
 client.rpc('brief_community_maintain').execute()
 print(f'Registered {len(rows)} public story identities; expired reading events removed.')
if __name__=='__main__':main()
