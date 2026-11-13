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
