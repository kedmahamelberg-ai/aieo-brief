const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const order = require('../assets/government-order.js');

function loadStripe(reducedMotion = false) {
  const saved = new Map();
  const timers = new Map();
  let nextTimer = 0;
  const node = () => ({hidden:false, dataset:{}, events:{}, classes:new Set(),
    classList:{add(name){this.owner.classes.add(name)},remove(name){this.owner.classes.delete(name)}},
    addEventListener(name,handler){this.events[name]=handler},
    setAttribute(name,value){this[name]=value},
    matches(){return false},contains(){return false}});
  const links = ['a','b','c'].map((key,index) => {
    const item = node(); item.classList.owner=item; item.dataset={key,date:index===2?'2026-09-01':'2026-11-17'}; return item;
  });
  const stripe=node(), run=node(), controls=node(), next=node(), pause=node();
  run.querySelectorAll=()=>links;
  run.replaceChildren=(...items)=>{run.children=items};
  const elements={'government-stripe-items':run,'government-stripe-controls':controls,
    'government-stripe-next':next,'government-stripe-pause':pause};
  const document={hidden:false,activeElement:null,events:{},querySelector:()=>stripe,
    getElementById:id=>elements[id],addEventListener(name,handler){this.events[name]=handler}};
  const motion={matches:reducedMotion,events:{},addEventListener(name,handler){this.events[name]=handler}};
  const context={document,window:{BriefGovernmentOrder:order,matchMedia:()=>motion},
    localStorage:{getItem:key=>saved.get(key),setItem:(key,value)=>saved.set(key,value)},
    crypto:{getRandomValues:array=>{array[0]=0;return array}},
    Date:class extends Date{constructor(...args){super(...(args.length?args:['2026-11-17T12:00:00Z']))}},
    Intl,Uint32Array,JSON,
    setTimeout(handler,delay){const id=++nextTimer;timers.set(id,{handler,delay});return id},
    clearTimeout(id){timers.delete(id)}};
  vm.runInNewContext(fs.readFileSync(require.resolve('../assets/government-stripe.js'),'utf8'),context);
  return {stripe,run,controls,next,pause,motion,timers,saved,
    fire:()=>{const [id,timer]=timers.entries().next().value;timers.delete(id);timer.handler()},
    visible:()=>run.children.filter(item=>!item.hidden)};
}

test('The bar includes older announcements and flips one upward every seven seconds',()=>{
  const view=loadStripe();
  assert.equal(view.visible().length,1);
  assert.equal(view.controls.hidden,false);
  assert.equal([...view.timers.values()][0].delay,7000);
  const first=view.visible()[0];
  view.fire();
  assert.equal(first.classes.has('is-leaving'),true);
  assert.equal(view.visible()[0],first);
  assert.equal([...view.timers.values()][0].delay,220);
  view.fire();
  assert.equal(view.visible().length,1);
  assert.notEqual(view.visible()[0],first);
  assert.equal(view.visible()[0].classes.has('is-entering'),true);
  assert.equal(view.run.children.length,3);
  view.pause.events.click();
  assert.equal(view.pause.textContent,'Play');
  assert.equal(view.timers.size,0);
  view.pause.events.click();
  assert.equal(view.pause.textContent,'Pause');
  assert.equal(view.timers.size,1);
});

test('Reduced-motion mode still changes stories automatically without animation',()=>{
  const view=loadStripe(true);
  assert.equal(view.pause.hidden,false);
  assert.equal([...view.timers.values()][0].delay,7000);
  const first=view.visible()[0];
  view.fire();
  assert.notEqual(view.visible()[0],first);
  assert.equal(view.visible()[0].classes.has('is-entering'),false);
  view.pause.events.click();
  assert.equal(view.timers.size,0);
});
