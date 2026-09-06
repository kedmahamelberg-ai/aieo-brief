const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
function worker(){
 const handlers={},shown=[],opened=[];
 const scope='https://example.test/aieo-brief/';
 const self={registration:{scope,showNotification:(title,opts)=>{shown.push({title,...opts});return Promise.resolve();}},
 clients:{claim:()=>Promise.resolve(),matchAll:()=>Promise.resolve([]),openWindow:url=>{opened.push(url);return Promise.resolve();}},
 addEventListener:(event,callback)=>handlers[event]=callback};
 vm.runInNewContext(fs.readFileSync('assets/news-worker.js','utf8'),{self,URL});
 return {handlers,shown,opened,scope};
}
test('push stays within the project and uses a stable edition tag',async()=>{
 const w=worker();let done;
 w.handlers.push({data:{json:()=>({title:'New edition',body:'News',url:'https://evil.test/',tag:'brief-edition-2026-W36'})},waitUntil:p=>done=p});
 await done;assert.equal(w.shown[0].data.url,w.scope);assert.equal(w.shown[0].tag,'brief-edition-2026-W36');assert.equal(w.shown[0].renotify,false);
});
test('notification opens the Brief project, never another GitHub Pages project',async()=>{
 const w=worker();let done;
 w.handlers.notificationclick({notification:{close(){},data:{url:'https://example.test/other-project/'}},waitUntil:p=>done=p});
 await done;assert.deepEqual(w.opened,[w.scope]);
});
test('worker does not intercept page fetches or manufacture notifications for malformed input',()=>{
 const w=worker();assert.equal(w.handlers.fetch,undefined);
 w.handlers.push({data:{json(){throw Error('invalid');}}});assert.equal(w.shown.length,0);
});
