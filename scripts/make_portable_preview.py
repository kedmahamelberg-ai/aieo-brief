#!/usr/bin/env python3
"""One downloadable file, real static pages, no server or accounts required."""
import argparse,base64,gzip,json,re
from pathlib import Path
from urllib.parse import urlsplit,unquote
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser();p.add_argument('--site',default='_site');p.add_argument('--output',required=True);args=p.parse_args();site=ROOT/args.site
 pages={x.relative_to(site).as_posix():x.read_text() for x in site.rglob('*.html')}
 # Bundle downloaded museum images; opening the preview needs no image host.
 for name,content in pages.items():
  def inline_image(match):
   value=match.group(1);parsed=urlsplit(value)
   if parsed.scheme or parsed.netloc:return match.group(0)
   path=(site/name).parent/unquote(parsed.path);path=path.resolve()
   if site.resolve() not in path.parents or not path.is_file():raise ValueError('Missing preview image: '+value)
   return 'src="data:image/jpeg;base64,'+base64.b64encode(path.read_bytes()).decode()+'"'
  pages[name]=re.sub(r'(?<=<img )src="([^"]+)"',inline_image,content)
 assets={name:(site/'assets'/name).read_text() for name in ('site.css','core.js','community.js','analytics.js','app.js')}
 payload=base64.b64encode(gzip.compress(json.dumps({'pages':pages,'assets':assets},ensure_ascii=False).encode(),mtime=0)).decode()
 html='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AIEO Brief · interactive preview</title><style>*{box-sizing:border-box}body{margin:0;background:#eef2f4;font:14px Arial,sans-serif;color:#142c3e}header{display:flex;align-items:center;gap:10px;padding:12px 18px;background:#142c3e;color:white;min-height:58px}header strong{margin-right:auto}button{border:1px solid #aab9c5;background:transparent;color:inherit;padding:9px 12px;border-radius:3px;cursor:pointer}button[aria-pressed=true]{background:white;color:#142c3e}iframe{display:block;width:100%;height:calc(100dvh - 58px);margin:auto;border:0;background:white}#status{padding:20px;text-align:center}@media(max-width:640px){header{flex-wrap:wrap}header strong{flex-basis:100%}iframe{height:calc(100dvh - 100px)}}:focus-visible{outline:3px solid #64d7c3;outline-offset:2px}</style><header><strong>The Brief · design and reading preview</strong><button id="home">News</button><button id="research">Research</button><button id="culture">A daily pause</button><button id="desktop" aria-pressed="true">Desktop</button><button id="mobile" aria-pressed="false">Mobile</button></header><p id="status">Opening the complete preview…</p><iframe title="AIEO Brief preview" id="preview" sandbox="allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox allow-downloads" hidden></iframe><script>
const packed='''+json.dumps(payload)+''';
(async()=>{try{
 const data=Uint8Array.from(atob(packed),c=>c.charCodeAt(0));
 const unpacked=await new Response(new Blob([data]).stream().pipeThrough(new DecompressionStream('gzip'))).text();const bundle=JSON.parse(unpacked),frame=document.getElementById('preview');let current='index.html';
 function escapeScript(s){return s.replace(/<\\/script/gi,'<\\\\/script');}
 function render(path){const fragment=path.split('#')[1]||'';path=path.split('#')[0]||'index.html';if(path.endsWith('/'))path+='index.html';if(!bundle.pages[path])return;current=path;let html=bundle.pages[path];
  html=html.replace('<head>','<head><base href="https://brief-preview.invalid/'+path+'">');
  html=html.replace(/<link rel="stylesheet"[^>]+>/,()=>'<style>'+bundle.assets['site.css']+'</style>');
  for(const name of ['core.js','community.js','analytics.js','app.js'])html=html.replace(new RegExp('<script src="[^"\\\\n]*assets/'+name.replace('.','\\\\.')+'" defer><\\\\/script>'),()=>'<script '+(name==='app.js'?'data-brief-root="https://brief-preview.invalid/"':'')+'>'+escapeScript(bundle.assets[name])+'<'+ '/script>');
  const nav=\"document.addEventListener('click',function(e){const a=e.target.closest('a[href]');if(!a)return;const u=new URL(a.href);if(u.origin==='https://brief-preview.invalid'){e.preventDefault();if(u.pathname.endsWith('feed.xml')){alert('The live RSS feed is included in the full website package.');return;}parent.postMessage({briefNavigate:u.pathname.slice(1)+u.hash},'*');}});\"+(fragment?\"setTimeout(()=>document.getElementById(\"+JSON.stringify(fragment)+\")?.scrollIntoView(),0);\":'');
  html=html.replace('</body>',()=>'<script>'+escapeScript(nav)+'<'+ '/script></body>');frame.srcdoc=html;frame.hidden=false;document.getElementById('status').hidden=true;
 }
 window.addEventListener('message',e=>{if(e.source===frame.contentWindow&&typeof e.data?.briefNavigate==='string')render(e.data.briefNavigate);});
 document.getElementById('home').onclick=()=>render('index.html');document.getElementById('research').onclick=()=>render('research/index.html');document.getElementById('culture').onclick=()=>render('culture/index.html');
 for(const mode of ['desktop','mobile'])document.getElementById(mode).onclick=()=>{frame.style.maxWidth=mode==='mobile'?'390px':'';document.getElementById('mobile').setAttribute('aria-pressed',String(mode==='mobile'));document.getElementById('desktop').setAttribute('aria-pressed',String(mode==='desktop'));};
 render('index.html');
 }catch(e){document.getElementById('status').textContent='Open this file in a recent Chrome, Edge, Firefox or Safari browser. You can also open Preview/index.html inside the update ZIP.';}})();
</script></html>'''
 Path(args.output).write_text(html,encoding='utf-8');print(json.dumps({'pages':len(pages),'bytes':Path(args.output).stat().st_size,'output':args.output}))
if __name__=='__main__':main()
