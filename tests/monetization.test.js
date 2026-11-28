const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('assets/analytics.js','utf8');const {create}=require('../owner-tools/monetization-settings.js');
function page(overrides={},desktop=false,headTag=false,options={}){let listener,reloads=0;const nodes=[],events=[];const ads={enabled:true,cmp_enabled:true,page_eligible:true,publisher_id:'ca-pub-5706650912346516',mode:'placements',...overrides};
 const slots=['feed','rail'].map(kind=>({dataset:{adKind:kind,adSlot:'12345'},hidden:true,children:[],querySelector(){return this.children[0]},querySelectorAll(){return this.children},appendChild(n){n.remove=()=>{this.children=[]};this.children.push(n)}}));
 const ids={'brief-config':{textContent:JSON.stringify({adsense:ads,is_preview:!!options.preview,ga4_measurement_id:'G-TEST'})},'analytics-consent':{},'consent-banner':{hidden:true}};
 const ctx={console,Date,JSON,CustomEvent:function(n,d){this.type=n;this.detail=d?.detail},localStorage:{getItem:()=>{if(options.storageBlocked)throw Error('blocked');return options.saved?JSON.stringify(options.saved):null;},setItem(){if(options.storageBlocked)throw Error('blocked')},removeItem(){}},location:{origin:'https://brief.hamelberg-ai.com',pathname:'/',hostname:'brief.hamelberg-ai.com',reload(){reloads++}},document:{title:'The Brief',cookie:'',head:{appendChild(n){nodes.push(n)}},getElementById:k=>ids[k],createElement:tag=>({tag,dataset:{},style:{}}),querySelectorAll:q=>q==='[data-ad-slot]'?slots:q==='script[src]'?nodes:[],querySelector:()=>({hidden:true}),addEventListener(){}},BriefCore:require('../assets/core.js'),BriefUX:{start(...args){events.push(args)},track(){}},navigator:{userAgent:options.userAgent||''},dispatchEvent(){},matchMedia:()=>({matches:desktop,addEventListener(){}}),__tcfapi:(op,version,cb)=>{listener=cb}};
 const listeners = new Map();
 ctx.addEventListener = ctx.document.addEventListener = (name, listener) => listeners.set(name, listener);
 ctx.emit = (name, event = {}) => listeners.get(name)?.(event);
 ctx.window=ctx;ctx.globalThis=ctx;
 if(headTag){nodes.push({src:'https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client='+ads.publisher_id});ctx.adsbygoogle=[];ctx.adsbygoogle.pauseAdRequests=1;}
 vm.runInNewContext(source,ctx);
 ctx.googlefc?.callbackQueue.find(c=>c.CONSENT_API_READY)?.CONSENT_API_READY();
 return {ctx,nodes,slots,ids,events,ads:()=>nodes.filter(n=>n.src?.includes('pagead2')),tcf:allowed=>listener({eventStatus:'useractioncomplete',gdprApplies:true,tcString:'test',purpose:{consents:{1:allowed}},vendor:{consents:{755:allowed}}},true),mode:status=>{ctx.googlefc.getGoogleConsentModeValues=()=>Object.fromEntries(['adStoragePurposeConsentStatus','adUserDataPurposeConsentStatus','adPersonalizationPurposeConsentStatus'].map(k=>[k,status]));ctx.googlefc.callbackQueue.find(c=>c.CONSENT_MODE_DATA_READY).CONSENT_MODE_DATA_READY()},reloads:()=>reloads};}
test('verification and source-only pages request no ads or CMP',()=>{for(const props of [{enabled:false},{page_eligible:false}]){const p=page(props);assert.equal(p.ads().length,0)}});
test('unknown or rejected advertising consent does not load ads, including after analytics opt-in',()=>{const p=page();assert.equal(p.ads().length,0);p.tcf(false);p.ctx.BriefAnalytics.choose(true);assert.equal(p.ads().length,0);const updates=p.ctx.dataLayer.filter(x=>x[0]==='consent'&&x[1]==='update');assert.ok(updates.every(x=>!('ad_storage' in x[2])))});
test('allowed consent fills each visible placement once and keeps the mobile rail hidden',()=>{const p=page();p.tcf(true);p.tcf(true);assert.equal(p.ads().length,1);assert.equal(p.slots[0].children.length,1);assert.equal(p.slots[1].children.length,0);assert.equal(p.slots[1].hidden,true)});
test('desktop rail, Auto mode and consent revocation are handled',()=>{const p=page({},true);p.tcf(true);assert.equal(p.slots[1].children.length,1);p.mode(2);assert.equal(p.reloads(),1);assert.ok(p.slots.every(s=>s.hidden));const auto=page({mode:'auto'});auto.mode(1);assert.equal(auto.ads().length,1);assert.equal(auto.slots[0].children.length,0)});
test('monetization form never enables ads before explicit setup confirmation',()=>{const v={update_ads:true,publisher_id:'ca-pub-5706650912346516',stage:'verify'};assert.equal(create(v).adsense.enabled,false);assert.throws(()=>create({...v,stage:'auto'}));assert.equal(create({...v,stage:'auto',approved:true,cmp:true}).adsense.enabled,true);assert.throws(()=>create({...v,stage:'placements',approved:true,cmp:true,feed:'bad'}));});
test('reader-support settings are a narrow patch with safe URLs',()=>{assert.deepEqual(create({update_support:true,support_url:'https://ko-fi.com/reader'}),{schema_version:'aieo_brief_monetization_v1',support_url:'https://ko-fi.com/reader'});for(const url of ['javascript:alert(1)','https://user:pass@example.com'])assert.throws(()=>create({update_support:true,support_url:url}))});

test('a paused head verification tag is reused exactly once after consent',()=>{const p=page({},false,true);assert.equal(p.ctx.adsbygoogle.pauseAdRequests,1);p.tcf(true);p.tcf(true);assert.equal(p.ads().length,1);assert.equal(p.ctx.adsbygoogle.pauseAdRequests,0);assert.equal(p.slots[0].children.length,1);p.tcf(false);assert.equal(p.ctx.adsbygoogle.pauseAdRequests,1)});
test('adding the head tag does not override disabled advertising or ineligible pages',()=>{for(const props of [{enabled:false},{cmp_enabled:false},{page_eligible:false}]){const p=page(props,false,true);assert.equal(p.ads().length,1);assert.equal(p.nodes.length,2);assert.equal(p.ctx.adsbygoogle.pauseAdRequests,1);assert.ok(p.slots.every(s=>s.children.length===0));}});

for(const [device,desktop,userAgent] of [['phone',false,'iPhone'],['tablet',false,'iPad'],['desktop',true,'Desktop']]) {
 test(device+': no analytics prompt; cookieless GA starts; private history stays optional',()=>{
  const p=page({enabled:false},desktop,false,{userAgent});
  const ga=()=>p.nodes.filter(n=>n.src && new URL(n.src).origin === 'https://www.googletagmanager.com');
  assert.equal(ga().length,1);
  assert.equal(p.ctx.BriefAnalytics.allowed(),true);
  assert.equal(p.ctx.BriefAnalytics.privateAllowed(),false);
  assert.equal(p.events.length,0);
  const defaultConsent=p.ctx.dataLayer.find(x=>x[0]==='consent'&&x[1]==='default');
  assert.equal(defaultConsent[2].analytics_storage,'denied');
  assert.equal(defaultConsent[2].ad_storage,'denied');
  assert.equal(p.ctx['ga-disable-G-TEST'],false);
  p.ctx.BriefAnalytics.event('source_open');
  assert.ok(p.ctx.dataLayer.some(x=>x[0]==='event'&&x[1]==='source_open'));
  p.ctx.BriefAnalytics.choose(true);
  assert.equal(p.ctx.BriefAnalytics.privateAllowed(),true);
  assert.equal(ga().length,1);
  p.ctx.BriefAnalytics.choose(false);
  assert.equal(p.ctx.BriefAnalytics.privateAllowed(),false);
  assert.equal(p.ctx.BriefAnalytics.allowed(),true);
  assert.equal(p.ctx.dataLayer.some(x=>x[0]==='consent'&&x[2]?.analytics_storage==='granted'),false);
 });
}
test('saved private-history choices do not affect cookieless GA; preview sends nothing',()=>{
 for(const analytics of [true,false]) {
  const p=page({enabled:false},false,false,{saved:{version:1,analytics,research:false,at:Date.now()}});
  assert.equal(p.ctx.BriefAnalytics.allowed(),true);
  assert.equal(p.ctx.BriefAnalytics.privateAllowed(),analytics);
  assert.equal(p.events.length,1);
 }
 for(const options of [{saved:{version:1,analytics:true,at:0}},{storageBlocked:true}]) {
  const p=page({enabled:false},false,false,options);
  assert.equal(p.ctx.BriefAnalytics.allowed(),true);
  assert.equal(p.ctx.BriefAnalytics.privateAllowed(),false);
  assert.equal(p.events.length,0);
  assert.equal(p.nodes.filter(n=>n.src && new URL(n.src).origin === 'https://www.googletagmanager.com').length,1);
 }
 const preview=page({enabled:false},false,false,{preview:true});
 assert.equal(preview.ctx.BriefAnalytics.allowed(),false);
 assert.ok(!preview.nodes.some(n=>n.src && new URL(n.src).origin === 'https://www.googletagmanager.com'));
 assert.doesNotMatch(fs.readFileSync('templates/base.html','utf8'),/id="consent-banner"/);
});

test('GA counts a visible cached navigation once and excludes preview restores', () => {
 for (const preview of [false, true]) {
  const {ctx} = page({}, false, false, {preview});
  const views = () => ctx.dataLayer.filter(call => call[0] === 'event' && call[1] === 'page_view').length;
  ctx.document.visibilityState = 'hidden';
  ctx.emit('pageshow', {persisted: false});
  ctx.emit('pageshow', {persisted: true});
  assert.equal(views(), preview ? 0 : 1);
  ctx.document.visibilityState = 'visible';
  ctx.emit('visibilitychange');
  ctx.emit('visibilitychange');
  assert.equal(views(), preview ? 0 : 2);
 }
});
