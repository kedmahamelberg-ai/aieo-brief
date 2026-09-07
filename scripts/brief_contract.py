"""Shared release binding, independent directions and publication configuration."""
from __future__ import annotations
import hashlib, json, os, re
from pathlib import Path
from urllib.parse import urlparse
DIRECTIONS = {'gain', 'loss', 'mixed', 'none', 'unresolved'}
PROMPT_VERSION = 'aieo-brief-editorial-v3-whole-evidence-independent-axes'
MARKETS = [('CA','Canada'),('CN','China'),('FR','France'),('GB','United Kingdom'),('US','United States')]

def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',',':')).encode()).hexdigest()

def relationship_fingerprint(relationship):
    # Do not trigger new editions just because a generation timestamp changed.
    return digest(sorted(relationship.get('evidence', []), key=lambda row: str(row.get('event_id', ''))))

def validate_pair(release, relationship):
    for key in ('release_id','period_start','period_end'):
        if not release.get(key) or release[key] != relationship.get(key):
            raise ValueError('Observatory releases do not match: '+key)
    if relationship.get('source_release_sha256') != release.get('content_sha256'):
        raise ValueError('Relationship data is bound to a different Observatory release.')
    ids = [str(x.get('effective_event_id') or x.get('event_id') or '') for x in release.get('evidence',[])]
    rows = relationship.get('evidence',[])
    rids = [str(x.get('event_id') or '') for x in rows]
    if not ids or '' in ids or len(set(ids))!=len(ids) or set(ids)!=set(rids) or len(rids)!=len(ids):
        raise ValueError('Every distinct development must have exactly one directional record.')
    published_count = (release.get('counts') or {}).get('ai_relevant_event_records')
    if published_count is not None and published_count != len(ids):
        raise ValueError('Development rows do not match the Observatory total.')
    counts = {a:{d:0 for d in sorted(DIRECTIONS)} for a in ('human','ai')}
    for row in rows:
        axes = row.get('axes') or {}
        for axis in counts:
            val = (axes.get(axis) or {}).get('direction')
            if val not in DIRECTIONS: raise ValueError('Missing independent '+axis+' direction: '+str(row.get('event_id')))
            counts[axis][val]+=1
    return counts

def fixed_relationship(row):
    axes=row.get('axes') or {}
    if any((axes.get(a) or {}).get('direction') not in DIRECTIONS for a in ('human','ai')):
        raise ValueError('Independent human and AI readings are required.')
    # Legacy database columns keep their existing vocabulary. The exact axes are
    # retained in evidence_basis_summary and never inferred from these columns.
    old={'gain':'enabling','loss':'constraining','mixed':'unclear','none':'neutral','unresolved':'unclear'}
    return {**row, 'human_direction':old[axes['human']['direction']],
            'ai_direction':old[axes['ai']['direction']], 'axes':axes,
            'configuration':row.get('configuration') or 'ambiguous_relational_signal'}

def safe_url(value, allow_mail=False, allow_http=False):
    value=str(value or '').strip()
    p=urlparse(value)
    if (p.scheme=='https' or (allow_http and p.scheme=='http')) and p.hostname and not p.username and not p.password: return value
    if allow_mail and p.scheme=='mailto' and '@' in p.path and not any(c in value for c in '\r\n'): return value
    return ''

def load_config(root):
    c=json.loads((Path(root)/'config/site.json').read_text())
    c.setdefault('personal_site_url', 'https://kedmahamelberg.com/')
    for key,env in [('site_url','BRIEF_SITE_URL'),('supabase_url','SUPABASE_URL'),('supabase_publishable_key','SUPABASE_PUBLISHABLE_KEY'),('ga4_measurement_id','GA4_MEASUREMENT_ID')]:
        if os.environ.get(env): c[key]=os.environ[env]
    if os.environ.get('BRIEF_COMMUNITY_ENABLED'): c['community_enabled']=os.environ['BRIEF_COMMUNITY_ENABLED'].lower()=='true'
    for key in ('site_url','observatory_url','personal_site_url','supabase_url','support_url','newsletter_url','privacy_contact_url'):
        if c.get(key) and not safe_url(c[key]): raise ValueError('Use an absolute HTTPS URL for '+key)
    for key in ('site_url','supabase_url'):
        parsed=urlparse(c.get(key,''))
        if parsed.query or parsed.fragment:raise ValueError('Do not put a query or fragment in '+key)
    pk=c.get('supabase_publishable_key','')
    if pk and not pk.startswith(('sb_publishable_','eyJ')): raise ValueError('Only the Supabase publishable/anon key belongs in site config.')
    if pk.startswith('eyJ'):
        import base64
        try: role=json.loads(base64.urlsafe_b64decode(pk.split('.')[1]+'==='))['role']
        except Exception: raise ValueError('Invalid Supabase anon key')
        if role!='anon': raise ValueError('A server key must never enter the browser configuration.')
    if c.get('community_enabled') and not (c.get('supabase_url') and pk):
        raise ValueError('Community enabled: supply SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY.')
    ga=c.get('ga4_measurement_id','')
    if ga and not re.fullmatch(r'G-[A-Z0-9]+',ga): raise ValueError('GA4 measurement ID must start G-.')
    ad=c.get('adsense') or {}
    for slot in (ad.get('slots') or {}).values():
        if slot and (not isinstance(slot,str) or not re.fullmatch(r'\d{1,20}',slot)):
            raise ValueError('Ad-unit IDs must contain only digits.')
    if ad.get('publisher_id') and not re.fullmatch(r'ca-pub-\d{16}',ad.get('publisher_id','')):raise ValueError('Invalid AdSense publisher ID')
    if ad.get('mode','auto') not in ('auto','placements'):raise ValueError('Choose auto or placements for advertising mode.')
    if ad.get('enabled'):
        if not c.get('site_url') or urlparse(c['site_url']).path.strip('/'):raise ValueError('Use the Brief’s domain root for AdSense and ads.txt.')
        if not re.fullmatch(r'ca-pub-\d{16}',ad.get('publisher_id','')): raise ValueError('Invalid AdSense publisher ID')
        if not ad.get('cmp_enabled'): raise ValueError('Set up the Google certified consent message before enabling AdSense.')
        if ad.get('mode','auto')=='placements' and not any(re.fullmatch(r'\d+',v or '') for v in ad.get('slots',{}).values()): raise ValueError('Add at least one AdSense ad-unit ID.')
    sponsor=c.get('sponsor',{})
    if sponsor.get('enabled') and not all(sponsor.get(k) for k in ('name','message','url','starts','ends')):
        raise ValueError('A sponsor needs a name, message, HTTPS link and campaign dates.')
    if sponsor.get('enabled'):
        from datetime import date
        if not safe_url(sponsor['url']):raise ValueError('Invalid sponsor URL')
        if date.fromisoformat(sponsor['ends'])<date.fromisoformat(sponsor['starts']):raise ValueError('Sponsor end date precedes its start')
        if len(sponsor['name'])>100 or len(sponsor['message'])>180:raise ValueError('Keep the sponsor message concise')
    return c
