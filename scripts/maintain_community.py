#!/usr/bin/env python3
"""Retention runs independently of news generation and publication."""
import os
from pathlib import Path
from brief_contract import load_config
from supabase import create_client
root=Path(__file__).resolve().parents[1]
if load_config(root).get('community_enabled'):
 client=create_client(os.environ['SUPABASE_URL'],os.environ['SUPABASE_SECRET_KEY'])
 result=client.rpc('brief_community_maintain').execute()
 print('Expired reading sessions removed:',result.data)
 print('Expired UX history removed:',client.rpc('brief_ux_maintain').execute().data)
else:print('Community is disabled; no database maintenance requested.')
