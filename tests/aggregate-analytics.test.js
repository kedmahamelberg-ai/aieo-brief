const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('assets/aggregate-analytics.js', 'utf8');

function run(navigator, options = {}) {
 const requests = [], listeners = {};
 const context = {
  URL, URLSearchParams, navigator,
  location: {
   hostname: 'brief.example',
   pathname: options.path || '/story/example/',
   search: options.query ?? '?email=private@example.com',
   hash: '#access_token=private'
  },
  fetch(url, init) { requests.push({url, ...init}); return Promise.resolve({ok: true}); },
  setInterval() {}, addEventListener: (name, fn) => listeners[name] = fn,
  document: {
   referrer: options.referrer || '',
   visibilityState: options.hidden ? 'hidden' : 'visible',
   body: {dataset: {}},
   getElementById: () => ({textContent: JSON.stringify({
    is_preview: Boolean(options.preview), is_redirect: Boolean(options.redirect), supabase_url: 'https://example.supabase.co',
    supabase_publishable_key: 'public'
   })}),
   addEventListener: (name, fn) => listeners[name] = fn
  }
 };
 context.window = context;
 vm.runInNewContext(source, context);
 return {context, requests, listeners};
}

for (const [device, navigator] of [
 ['desktop', {userAgent: 'Mozilla/5.0 (Windows NT 10.0)'}],
 ['mobile', {userAgent: 'iPhone Mobile'}],
 ['tablet', {userAgent: 'iPad'}],
 ['tablet', {userAgent: 'Macintosh', maxTouchPoints: 5}],
 ['tablet', {userAgent: 'Android 14'}],
 ['other', {userAgent: 'Console'}]
]) {
 test(device + ' sends a single visible page view without identity or cookies', () => {
  const {context, requests, listeners} = run(navigator);
  const [request] = requests;
  assert.match(request.url, /\/brief_record_page_view$/);
  assert.deepEqual(JSON.parse(request.body), {
   p_device: device, p_path: '/story/example/', p_source: 'direct_or_unknown'
  });
  assert.equal(request.credentials, 'omit');
  assert.equal(request.referrerPolicy, 'no-referrer');
  assert.equal(request.headers.Authorization, undefined);
  assert.ok(!JSON.stringify(request).includes('private'));
  listeners.visibilitychange();
  context.BriefAggregate.event('page_view');
  assert.equal(requests.length, 1);
  context.BriefAggregate.event('source_open', {email: 'private'});
  assert.match(requests[1].url, /\/brief_record_aggregate$/);
  assert.deepEqual(JSON.parse(requests[1].body), {
   p_device: device, p_path: '/story/example/', p_event: 'source_open'
  });
  context.BriefAggregate.event('unknown');
  assert.equal(requests.length, 2);
 });
}

for (const [expected, referrer, query] of [
 ['google', 'https://www.google.co.uk/search?q=private', ''],
 ['chatgpt', 'https://chatgpt.com/c/private', ''],
 ['chatgpt', '', '?utm_source=chatgpt.com&utm_campaign=private'],
 ['claude', 'https://claude.ai/chat/private', ''],
 ['claude', '', '?utm_source=CLAUDE.AI&note=private'],
 ['internal', 'https://brief.example/story/private/', '?utm_source=claude.ai'],
 ['other_referral', 'https://chatgpt.com.example.org/private', ''],
 ['direct_or_unknown', '', '?utm_source=claude.ai.example.org']
]) {
 test('classifies ' + expected + ' without transmitting the original input', () => {
  const {requests} = run({userAgent: 'iPhone'}, {referrer, query});
  assert.equal(JSON.parse(requests[0].body).p_source, expected);
  assert.ok(!JSON.stringify(requests).includes('private'));
 });
}

test('previews, crawlers and unsafe paths never record', () => {
 for (const example of [
  run({userAgent: 'Googlebot'}),
  run({userAgent: 'ChatGPT-User'}),
  run({userAgent: 'Claude-User'}),
  run({userAgent: 'iPhone'}, {preview: true}),
  run({userAgent: 'iPhone'}, {path: '/auth/user@example.com/'})
 ]) assert.equal(example.requests.length, 0);
});

test('background tabs wait for a visible visit and HTML routes use the public path', () => {
 const {context, requests, listeners} = run({userAgent: 'iPhone'}, {
  hidden: true, path: '/story/example/index.html'
 });
 assert.equal(requests.length, 0);
 context.document.visibilityState = 'visible';
 listeners.visibilitychange();
 assert.equal(requests.length, 1);
 assert.equal(JSON.parse(requests[0].body).p_path, '/story/example/');
});

test('counts the destination once and a visible return from browser history once', () => {
 const nav = {userAgent: 'iPhone'};
 assert.equal(run(nav, {redirect: true}).requests.length, 0);
 const {requests, listeners, context} = run(nav);
 listeners.pageshow({persisted: false});
 listeners.visibilitychange();
 assert.equal(requests.length, 1);
 context.document.visibilityState = 'hidden';
 listeners.pageshow({persisted: true});
 assert.equal(requests.length, 1);
 context.document.visibilityState = 'visible';
 listeners.visibilitychange();
 listeners.visibilitychange();
 assert.equal(requests.length, 2);
 assert.equal(JSON.parse(requests[1].body).p_source, 'direct_or_unknown');
});
