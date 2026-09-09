#!/usr/bin/env python3
"""Publish only the story allowlist for community interactions; never source bodies."""
import json,os
from pathlib import Path
from supabase import create_client
from brief_contract import load_config
from english_publication import content_version,LAYOUT
ROOT=Path(__file__).resolve().parents[1]
def main():
 config=load_config(ROOT)
 if not config.get('community_enabled'): print('Community is disabled; registration skipped.');return
 client=create_client(os.environ['SUPABASE_URL'],os.environ['SUPABASE_SECRET_KEY'])
 base=config.get('site_url')
 if not base:
  owner,repo=os.environ['GITHUB_REPOSITORY'].split('/',1);base=f'https://{owner}.github.io/{repo}'
 archive=ROOT/'_site/data/public-items.json'
 if not archive.exists():raise ValueError('Build the site with --update-archive before registering its stories.')
 stories=json.loads(archive.read_text())['items']
 rows=[{'story_key':s['key'],'headline':s['headline'],'url':base.rstrip('/')+'/'+s['path'].removesuffix('index.html'),'kind':s['kind'],'published_date':s['date']} for s in stories]
 for start in range(0,len(rows),100):client.table('brief_community_items').upsert(rows[start:start+100],on_conflict='story_key').execute()
 versions=[{'content_hash':content_version(s)[0],'story_key':s['key'],'layout_version':LAYOUT,'snapshot':content_version(s)[1]} for s in stories]
 for start in range(0,len(versions),100):client.table('brief_ux_content_versions').upsert(versions[start:start+100],on_conflict='content_hash',ignore_duplicates=True).execute()
 client.rpc('brief_community_maintain').execute()
 client.rpc('brief_ux_maintain').execute()
 print(f'Registered {len(rows)} public story identities; expired reading events removed.')
if __name__=='__main__':main()
