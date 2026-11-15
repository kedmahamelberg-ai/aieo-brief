const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('assets/aggregate-analytics.js','utf8');
function run(nav,options={}) {
 const requests=[],listeners={};
 const ctx={JSON,Set,innerHeight:800,location:{pathname:options.path||'/story/example/',search:'?email=private@example.com',hash:'#access_token=private'},navigator:nav,fetch:(url,opts)=>{requests.push({url,...opts});return Promise.resolve({ok:true});},setInterval(){},document:{visibilityState:options.hidden?'hidden':'visible',body:{dataset:{}},getElementById:()=>({textContent:JSON.stringify({is_preview:!!options.preview,supabase_url:'https://example.supabase.co',supabase_publishable_key:'public'})}),addEventListener:(n,fn)=>listeners[n]=fn}};
 ctx.window=ctx;vm.runInNewContext(source,ctx);return {ctx,requests,listeners};
}
for(const [device,nav] of [['desktop',{userAgent:'Mozilla/5.0 (Windows NT 10.0)'}],['mobile',{userAgent:'iPhone Mobile'}],['tablet',{userAgent:'iPad'}],['tablet',{userAgent:'Macintosh',maxTouchPoints:5}],['tablet',{userAgent:'Android 14'}],['other',{userAgent:'Console'}]]) {
 test(device+' counts automatically without storage, account tokens or queries',()=>{const p=run(nav);assert.equal(p.requests.length,1);const request=p.requests[0],body=JSON.parse(request.body);assert.equal(body.p_device,device);assert.deepEqual(Object.keys(body).sort(),['p_device','p_event','p_path']);assert.equal(request.credentials,'omit');assert.equal(request.referrerPolicy,'no-referrer');assert.equal(request.headers.Authorization,undefined);assert.ok(!JSON.stringify(request).includes('private'));p.listeners.visibilitychange();assert.equal(p.requests.length,1);p.ctx.BriefAggregate.event('source_open',{email:'private'});assert.equal(p.requests.length,2);p.ctx.BriefAggregate.event('unknown');assert.equal(p.requests.length,2);});
}
test('previews, crawlers and unsafe paths never record',()=>{for(const p of [run({userAgent:'Googlebot'}),run({userAgent:'iPhone'},{preview:true}),run({userAgent:'iPhone'},{path:'/auth/user@example.com/'})])assert.equal(p.requests.length,0);});
test('background tabs wait for a visible visit',()=>{const p=run({userAgent:'iPhone'},{hidden:true});assert.equal(p.requests.length,0);p.ctx.document.visibilityState='visible';p.listeners.visibilitychange();assert.equal(p.requests.length,1);});
