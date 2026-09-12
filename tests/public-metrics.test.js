'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.resolve(__dirname,'..');
const Core=require('../assets/core.js');
for(const value of [0,1,2,undefined,null,-1,NaN,Infinity,2.5,'3',true,{},Number.MAX_SAFE_INTEGER+1]){
 test('hide non-public count '+String(value),()=>assert.equal(Core.publicMetricNumber(value),null));
}
for(const value of [3,4,25,1234]){
 test('publish actual count '+value,()=>assert.equal(Core.publicMetricNumber(value),value));
}
function makeRow(key){
 const names=['views','likes','comments','shares','saves','reads'];
 const nodes=names.map(metric=>({dataset:{metric},textContent:'',parentElement:{hidden:true}}));
 return {dataset:{publicMetrics:key},hidden:true,nodes,querySelectorAll:()=>nodes};
}
function engagementHarness(){
 const key='event:00000000-0000-0000-0000-000000000000',row=makeRow(key),handlers={},intervals=[];
 let result={},fail=false,calls=[];
 const window={BriefCore:Core,BriefAnalytics:{allowed:()=>false},BriefCommunity:{enabled:true,
 metrics:async keys=>{calls.push(keys);if(fail)throw new Error('unavailable');return result;},rpc:()=>{throw new Error('No engagement writes in display tests');}},
 addEventListener:(n,f)=>(handlers[n]||=[]).push(f),dispatchEvent:e=>(handlers[e.type]||[]).forEach(f=>f(e))};
 const document={hidden:false,body:{dataset:{}},querySelectorAll:()=>[row],addEventListener:()=>{}};
 const context={window,document,Intl,Number,Set,Date,crypto:{randomUUID:()=>key},setInterval:f=>intervals.push(f),
 CustomEvent:function(type,options){this.type=type;this.detail=options.detail;}};
 vm.runInNewContext(fs.readFileSync(path.join(root,'assets/engagement.js'),'utf8'),context);
 return {key,row,window,handlers,calls,set:value=>{result=value;},fail:()=>{fail=true;},tick:()=>new Promise(r=>setImmediate(r))};
}
test('each statistic is independently hidden; no empty strip or info link',async()=>{
 const h=engagementHarness();await h.tick();
 h.window.dispatchEvent({type:'brief-metrics',detail:{[h.key]:{views:20,likes:2,comments:0,shares:3,saves:1,reads:2}}});
 assert.equal(h.row.hidden,false);
 assert.deepEqual(h.row.nodes.map(n=>!n.parentElement.hidden),[true,false,false,true,false,false]);
 assert.deepEqual(h.row.nodes.map(n=>n.textContent),['20','','','3','','']);
 h.window.dispatchEvent({type:'brief-metrics',detail:{[h.key]:{views:2,shares:2}}});
 assert.equal(h.row.hidden,true);
 assert.ok(h.row.nodes.every(n=>n.textContent===''&&n.parentElement.hidden));
});
test('polling announces updated metrics to both display renderers',async()=>{
 const h=engagementHarness();await h.tick();h.set({[h.key]:{views:3}});
 await h.window.BriefEngagement.refresh();assert.equal(h.row.nodes[0].textContent,'3');
 assert.equal(h.row.hidden,false);
});
test('unavailable metrics do not fabricate zero counts',async()=>{
 const h=engagementHarness();await h.tick();h.fail();await h.window.BriefEngagement.refresh();
 assert.equal(h.row.hidden,true);assert.ok(h.row.nodes.every(n=>n.textContent===''));
});
test('display does not mutate stored values or start a measurement',async()=>{
 const h=engagementHarness();await h.tick();const m=Object.freeze({views:2,likes:3});
 h.window.dispatchEvent({type:'brief-metrics',detail:Object.freeze({[h.key]:m})});
 assert.equal(m.views,2);assert.equal(m.likes,3);
});
const app=fs.readFileSync(path.join(root,'assets/app.js'),'utf8');
function badgeHarness(m){
 const key='test',read={dataset:{readCount:key},textContent:'',hidden:true},like={dataset:{likeCount:key}},comment={dataset:{commentCount:key}};
 const buttons=[{dataset:{key},setAttribute:()=>{}}];
 const document={querySelectorAll:s=>s==='[data-read-count]'?[read]:s==='[data-like-count]'?[like]:s==='[data-comment-count]'?[comment]:buttons};
 const context={document,Core,metrics:{[key]:m},isSaved:()=>false};
 const line=app.split('\n').find(s=>s.startsWith(' function refreshButtons(){'));
 assert.ok(line);vm.runInNewContext(line+';refreshButtons();',context);return {read,like,comment};
}
test('Like, Discuss and duplicate read labels share the threshold',()=>{
 const low=badgeHarness({reads:2,likes:1,comments:0});
 assert.ok(Object.values(low).every(n=>n.hidden&&n.textContent===''));
 const high=badgeHarness({reads:3,likes:4,comments:5});
 assert.equal(high.read.textContent,'3 reads this week');assert.equal(high.like.textContent,'4');assert.equal(high.comment.textContent,'5');
 assert.ok(Object.values(high).every(n=>!n.hidden));
});
test('public comments and popularity also use the same threshold',()=>{
 assert.ok(app.includes('Core.publicMetricNumber(rows.length)!==null'));
 assert.ok(app.includes('.filter(i=>Core.publicMetricNumber(metrics[i.key]?.reads)!==null)'));
 assert.ok(app.includes("window.addEventListener('brief-metrics',"));
});
test('shared template hides initial placeholders without hiding action buttons',()=>{
 const t=fs.readFileSync(path.join(root,'templates/components.html'),'utf8');
 assert.match(t,/data-public-metrics="\{\{ item.key \}\}"[^>]+hidden>/);
 assert.equal((t.match(/<span hidden><strong data-metric=/g)||[]).length,6);
 assert.match(t,/data-like-count="\{\{ item.key \}\}" hidden/);
 assert.match(t,/data-comment-count="\{\{ item.key \}\}" hidden/);
 for(const action of ['like','share','save'])assert.match(t,new RegExp('<button[^>]+data-action="'+action+'"'));
 assert.ok(t.includes('Discuss'));assert.ok(!t.includes('>—</strong>'));
});
