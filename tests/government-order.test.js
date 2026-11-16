const test = require('node:test');
const assert = require('node:assert/strict');
const order = require('../assets/government-order.js');
test('Weekly overview includes the entire current week and preserves publication dates', () => {
  const items = [{key:'old',date:'2026-11-08'},{key:'monday',date:'2026-11-09'},{key:'today',date:'2026-11-13'},{key:'future',date:'2026-11-14'}];
  const result = order.week(items,'2026-11-13');
  assert.equal(result.current,true);
  assert.deepEqual(result.items.map(x=>x.key),['monday','today']);
  assert.equal(items[1].date,'2026-11-09');
});
test('A quiet new week retains the latest available week without relabelling it current', () => {
  const result = order.week([{key:'a',date:'2026-11-13'},{key:'b',date:'2026-11-06'}],'2026-11-16');
  assert.equal(result.current,false);
  assert.deepEqual(result.items.map(x=>x.key),['a']);
});
test('A new entrance changes repeated order without dropping or duplicating stories', () => {
  const items = [{key:'a'},{key:'b'},{key:'c'}];
  const result = order.shuffle(items,['a','b','c'],()=>.999);
  assert.notDeepEqual(result.map(x=>x.key),['a','b','c']);
  assert.deepEqual(result.map(x=>x.key).sort(),['a','b','c']);
  assert.deepEqual(items.map(x=>x.key),['a','b','c']);
});
test('Empty and single-story weeks remain valid', () => {
  assert.deepEqual(order.week([],'2026-11-13').items,[]);
  assert.deepEqual(order.shuffle([{key:'a'}],['a']),[{key:'a'}]);
});

const fs = require('node:fs');
const vm = require('node:vm');
function overview(rows, search = '?view=day', now = '2026-11-16T12:00:00Z') {
  const makeNode = () => ({children:[],hidden:false,dataset:{},events:{},
    append(...nodes) {this.children.push(...nodes);},
    setAttribute(name,value) {this[name]=value;},
    addEventListener(name,handler) {this.events[name]=handler;}});
  const cards = rows.map(row => {
    const card = makeNode(); card.dataset = {...row,displayDate:row.date};
    const heading = makeNode(); card.querySelector = () => heading; return card;
  });
  const feed = makeNode();
  feed.querySelectorAll = () => cards;
  feed.replaceChildren = fragment => {feed.children = fragment.children;};
  const country = makeNode(); country.value='all';
  country.options = ['all',...new Set(rows.map(row=>row.country))].map(value=>({value}));
  const buttons = ['day','country','archive'].map(view=>({...makeNode(),dataset:{governmentView:view}}));
  const status = makeNode(), controls = makeNode(), countryControl = makeNode();
  const document = {
    getElementById: id => ({'government-feed':feed,'government-country':country,'government-status':status})[id],
    querySelectorAll: () => buttons,
    querySelector: selector => selector==='[data-country-control]' ? countryControl : controls,
    createDocumentFragment: makeNode,
    createElement: makeNode,
  };
  const stored = new Map();
  vm.runInNewContext(fs.readFileSync(require.resolve('../assets/governments.js'),'utf8'), {
    document, window:{BriefGovernmentOrder:order}, URLSearchParams,
    Date:class extends Date {constructor(...args) {super(...(args.length ? args : [now]));}},
    location:{search,pathname:'/governments-say/',hash:''}, history:{replaceState(){}},
    localStorage:{getItem:key=>stored.get(key),setItem:(key,value)=>stored.set(key,value)},
    crypto:{getRandomValues:array=>{array[0]=1;return array;}},
  });
  return {cards,feed,country,buttons,status,visible:()=>cards.filter(card=>!card.hidden)};
}
test('Monday imports keep the preceding six days visible and every original card in the archive', () => {
  const rows = [
    {key:'september',date:'2026-09-30',country:'ES',countryName:'Spain'},
    {key:'outside',date:'2026-11-09',country:'GB',countryName:'United Kingdom'},
    {key:'boundary',date:'2026-11-10',country:'GB',countryName:'United Kingdom'},
    {key:'sunday',date:'2026-11-15',country:'EE',countryName:'Estonia'},
    {key:'monday-mt',date:'2026-11-16',country:'MT',countryName:'Malta'},
    {key:'monday-sk',date:'2026-11-16',country:'SK',countryName:'Slovakia'},
  ];
  const page = overview(rows);
  assert.deepEqual(page.visible().map(card=>card.dataset.key),rows.slice(2).map(row=>row.key));
  assert.deepEqual(page.feed.children.filter(group=>!group.hidden).map(group=>group.children[0].textContent),['2026-11-16','2026-11-15','2026-11-10']);
  assert.match(page.status.textContent,/4 Monitor AI narratives · last 7 days/);
  page.buttons[2].events.click();
  assert.deepEqual(page.visible(),page.cards);
  assert.match(page.status.textContent,/6 Monitor AI narratives · all published dates/);
  const displayed = page.feed.children.flatMap(group=>group.children.slice(1));
  assert.equal(new Set(displayed).size,6);
  assert.ok(page.cards.every(card=>displayed.includes(card)));
  assert.equal(overview(rows,'?view=archive').visible().length,6);
});
test('Country filtering retains old identities and returning to seven days restores the date filter', () => {
  const page = overview([
    {key:'old-malta',date:'2026-10-01',country:'MT',countryName:'Malta'},
    {key:'new-malta',date:'2026-11-16',country:'MT',countryName:'Malta'},
    {key:'slovakia',date:'2026-11-16',country:'SK',countryName:'Slovakia'},
  ]);
  const original = [...page.cards];
  page.buttons[1].events.click(); page.country.value='MT'; page.country.events.change();
  assert.deepEqual(page.visible(),original.slice(0,2));
  page.buttons[0].events.click();
  assert.deepEqual(page.visible(),original.slice(1));
  page.buttons[2].events.click();
  assert.deepEqual(page.visible(),original);
});
test('The seven-day boundary follows Amsterdam midnight across daylight saving and month changes', () => {
  for (const [now,first,today] of [
    ['2026-11-15T23:30:00Z','2026-11-10','2026-11-16'],
    ['2026-10-25T23:30:00Z','2026-10-20','2026-10-26'],
    ['2026-03-29T22:30:00Z','2026-03-24','2026-03-30'],
    ['2027-01-01T00:30:00Z','2026-12-26','2027-01-01'],
  ]) {
    const before = new Date(first+'T00:00:00Z'); before.setUTCDate(before.getUTCDate()-1);
    const after = new Date(today+'T00:00:00Z'); after.setUTCDate(after.getUTCDate()+1);
    const page = overview([before.toISOString().slice(0,10),first,today,after.toISOString().slice(0,10)].map((date,i)=>({key:String(i),date,country:'MT',countryName:'Malta'})),'?view=day',now);
    assert.deepEqual(page.visible().map(card=>card.dataset.date),[first,today]);
  }
});
test('Quiet periods keep older announcements available with an explicit archive prompt', () => {
  const page = overview([{key:'old',date:'2026-11-01',country:'MT',countryName:'Malta'}]);
  assert.equal(page.visible().length,0);
  assert.match(page.status.textContent,/Select All dates/);
  page.buttons[2].events.click();
  assert.deepEqual(page.visible(),page.cards);
});
