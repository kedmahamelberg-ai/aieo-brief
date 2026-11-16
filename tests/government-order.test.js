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
function overview(rows, search = '?view=day') {
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
  const buttons = ['day','country'].map(view=>({...makeNode(),dataset:{governmentView:view}}));
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
    location:{search,pathname:'/governments-say/',hash:''}, history:{replaceState(){}},
    localStorage:{getItem:key=>stored.get(key),setItem:(key,value)=>stored.set(key,value)},
    crypto:{getRandomValues:array=>{array[0]=1;return array;}},
  });
  return {cards,feed,country,buttons,status,visible:()=>cards.filter(card=>!card.hidden)};
}
test('New Monday imports retain every older date in Day overview', () => {
  const previous = [
    {key:'september',date:'2026-09-30',country:'ES',countryName:'Spain'},
    {key:'last-week',date:'2026-11-13',country:'GB',countryName:'United Kingdom'},
    {key:'sunday',date:'2026-11-15',country:'EE',countryName:'Estonia'},
  ];
  const added = [
    {key:'monday-mt',date:'2026-11-16',country:'MT',countryName:'Malta'},
    {key:'monday-sk',date:'2026-11-16',country:'SK',countryName:'Slovakia'},
  ];
  assert.equal(overview(previous).visible().length,3);
  const page = overview([...previous,...added]);
  assert.deepEqual(page.visible().map(card=>card.dataset.key).sort(),[...previous,...added].map(row=>row.key).sort());
  assert.deepEqual(page.feed.children.map(group=>group.children[0].textContent),['2026-11-16','2026-11-15','2026-11-13','2026-09-30']);
  assert.match(page.status.textContent,/5 Monitor AI narratives/);
  assert.match(page.status.textContent,/all published dates/);
  const displayed = page.feed.children.flatMap(group=>group.children.slice(1));
  assert.equal(new Set(displayed).size,5);
  assert.ok(page.cards.every(card=>displayed.includes(card)));
});
test('Country filtering and returning to Day overview retain old article identities', () => {
  const page = overview([
    {key:'old-malta',date:'2026-10-01',country:'MT',countryName:'Malta'},
    {key:'new-malta',date:'2026-11-16',country:'MT',countryName:'Malta'},
    {key:'slovakia',date:'2026-11-16',country:'SK',countryName:'Slovakia'},
  ]);
  const original = [...page.cards];
  page.buttons[1].events.click(); page.country.value='MT'; page.country.events.change();
  assert.deepEqual(page.visible(),original.slice(0,2));
  page.buttons[0].events.click();
  assert.deepEqual(page.visible(),original);
  assert.ok(page.feed.children.every(group=>!group.hidden));
});
