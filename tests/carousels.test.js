const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

// Small DOM fixture: exercise event order and timers without paid or network calls.
function fixture(reducedMotion = false) {
  class Element {
    constructor() { this.listeners = {}; this.hidden = false; this.attributes = {}; this.textContent = ''; }
    addEventListener(name, fn) { (this.listeners[name] ||= []).push(fn); }
    fire(name, event = {}) { for (const fn of this.listeners[name] || []) fn({detail: 0, ...event}); }
    setAttribute(name, value) { this.attributes[name] = value; }
  }
  const root = new Element(), doc = new Element(), reduced = new Element();
  const slides = [new Element(), new Element(), new Element()];
  const links = [new Element()];
  const controls = Object.fromEntries(['controls','pause','position','status','prev','next'].map(k => [k, new Element()]));
  const timers = new Map(); let sequence = 0, intersection;
  root.dataset = {carousel: 'culture'}; root.classList = {add() {}};
  root.querySelectorAll = s => s === '[data-carousel-slide]' ? slides : links;
  root.querySelector = s => controls[s.slice('[data-carousel-'.length, -1)];
  doc.querySelectorAll = () => [root]; doc.hidden = false; reduced.matches = reducedMotion;
  const events = [];
  const window = {matchMedia: () => reduced, IntersectionObserver: true, BriefAnalytics: {event: (...args) => events.push(args)}};
  const ctx = {window, document: doc, setInterval: fn => { timers.set(++sequence, fn); return sequence; }, clearInterval: id => timers.delete(id),
    IntersectionObserver: class { constructor(fn) {intersection = fn;} observe() {}}};
  vm.runInNewContext(fs.readFileSync(require.resolve('../assets/carousels.js'), 'utf8'), ctx);
  return {root, doc, slides, controls, reduced, timers, events, links,
    tick: () => [...timers.values()].forEach(fn => fn()),
    visibility: value => intersection([{isIntersecting: value}])};
}

test('automatic slides have one focusable panel and do not announce every rotation', () => {
  const f = fixture(); assert.equal(f.timers.size, 1); f.tick();
  assert.deepEqual(f.slides.map(s => s.hidden), [true, false, true]);
  assert.equal(f.controls.position.textContent, '2 / 3');
  assert.equal(f.controls.status.textContent, '');
});

test('Pause click stays paused when pointer focus fires before click; Play resumes', () => {
  const f = fixture(); const pause = f.controls.pause;
  pause.fire('pointerdown'); f.root.fire('focusin'); pause.fire('click', {detail: 1});
  assert.equal(f.timers.size, 0); assert.equal(pause.textContent, 'Play');
  pause.fire('pointerdown'); pause.fire('click', {detail: 1});
  assert.equal(f.timers.size, 1); assert.equal(pause.textContent, 'Pause');
});

test('keyboard and manual navigation pause until Play and wrap in either direction', () => {
  const f = fixture(); f.root.fire('focusin'); assert.equal(f.timers.size, 0);
  f.controls.prev.fire('click'); assert.equal(f.controls.position.textContent, '3 / 3');
  f.controls.next.fire('click'); assert.equal(f.controls.position.textContent, '1 / 3');
  let prevented = false;
  f.root.fire('keydown', {key: 'ArrowRight', target: {closest: () => null}, preventDefault: () => {prevented = true;}});
  assert.ok(prevented); assert.equal(f.controls.position.textContent, '2 / 3');
  assert.match(f.controls.status.textContent, /item 2 of 3/);
  assert.equal(f.timers.size, 0); f.controls.pause.fire('click'); assert.equal(f.timers.size, 1);
});

test('hover, hidden tabs and offscreen panels suspend timers without losing the slide', () => {
  const f = fixture(); f.root.fire('mouseenter'); assert.equal(f.timers.size, 0);
  f.root.fire('mouseleave'); assert.equal(f.timers.size, 1);
  f.doc.hidden = true; f.doc.fire('visibilitychange'); assert.equal(f.timers.size, 0);
  f.doc.hidden = false; f.doc.fire('visibilitychange'); assert.equal(f.timers.size, 1);
  f.visibility(false); assert.equal(f.timers.size, 0); f.visibility(true); assert.equal(f.timers.size, 1);
});

test('reduced motion prevents rotation but allows manual discovery; analytics uses consent wrapper', () => {
  const f = fixture(true); assert.equal(f.timers.size, 0); assert.equal(f.controls.pause.disabled, true);
  f.controls.next.fire('click'); assert.equal(f.controls.position.textContent, '2 / 3');
  f.links[0].fire('click'); assert.equal(f.events[0][0], 'feature_open');
  assert.equal(f.events[0][1].placement, 'culture');
});
