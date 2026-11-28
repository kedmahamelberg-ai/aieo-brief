/* Aggregate audience counts: no cookies, storage, visitor IDs or account tokens. */
(function () {
 'use strict';
 const config = JSON.parse(document.getElementById('brief-config').textContent);
 const events = new Set(['engaged_read', 'source_open', 'share_option', 'save', 'unsave', 'like', 'unlike', 'support_link']);
 const path = location.pathname.replace(/\/index\.html$/, '/');
 const bot = /bot\b|spider|crawler|headless|ChatGPT-User|Claude-User/i;
 const namedSources = new Map([
  ['google', 'google'], ['google.com', 'google'],
  ['chatgpt', 'chatgpt'], ['chatgpt.com', 'chatgpt'], ['chat.openai.com', 'chatgpt'],
  ['claude', 'claude'], ['claude.ai', 'claude'], ['claude.com', 'claude']
 ]);

 function deviceClass(nav) {
  const ua = nav.userAgent || '';
  if (bot.test(ua)) return 'other';
  if (/iPad|Tablet|Kindle|Silk|PlayBook/i.test(ua) || (/Macintosh/i.test(ua) && nav.maxTouchPoints > 1) || (/Android/i.test(ua) && !/Mobile/i.test(ua))) return 'tablet';
  if (nav.userAgentData?.mobile || /Mobi|iPhone|iPod|Android|Windows Phone/i.test(ua)) return 'mobile';
  if (/Windows|Macintosh|Linux|CrOS|X11/i.test(ua)) return 'desktop';
  return 'other';
 }

 function landingSource(referrer, query) {
  let host = '';
  try {
   const url = new URL(referrer);
   if (url.protocol === 'https:' || url.protocol === 'http:') host = url.hostname;
  } catch {}
  if (host && host === location.hostname) return 'internal';

  const domain = host.replace(/^www\./, '');
  if (/^google\.(?:com|[a-z]{2,3}|(?:co|com)\.[a-z]{2})$/.test(domain)) return 'google';
  const referral = namedSources.get(domain);
  if (referral) return referral;

  const tag = new URLSearchParams(query).get('utm_source')?.trim().toLowerCase();
  return namedSources.get(tag) || (host ? 'other_referral' : 'direct_or_unknown');
 }

 const device = deviceClass(navigator);
 let source = landingSource(document.referrer, location.search);
 const active = !config.is_preview && !config.is_redirect && config.supabase_url && config.supabase_publishable_key
  && path.length <= 240 && /^\/(?:[a-z0-9-]+\/)*$/.test(path) && !bot.test(navigator.userAgent || '');
 let sentView = false, sentRead = false, visibleSeconds = 0;

 function record(rpc, body) {
  return fetch(config.supabase_url + '/rest/v1/rpc/' + rpc, {
   method: 'POST',
   credentials: 'omit',
   referrerPolicy: 'no-referrer',
   keepalive: true,
   headers: {apikey: config.supabase_publishable_key, 'Content-Type': 'application/json'},
   body: JSON.stringify(body)
  }).then(response => response.ok, () => false);
 }

 function event(name) {
  if (active && events.has(name)) {
   record('brief_record_aggregate', {p_path: path, p_device: device, p_event: name});
  }
 }

 function view() {
  if (!active || sentView || document.visibilityState !== 'visible') return;
  sentView = true;
  record('brief_record_page_view', {p_path: path, p_device: device, p_source: source}).then(saved => {
   if (saved && document.body.dataset.storyKey) window.dispatchEvent(new CustomEvent('brief-metrics-refresh'));
  });
 }

 view();
 document.addEventListener('visibilitychange', view);
 window.addEventListener('pageshow', e => {
  if (e.persisted) {
   source = 'direct_or_unknown';
   sentView = false;
   view();
  }
 });
 if (active && document.body.dataset.storyKey) setInterval(() => {
  if (document.visibilityState !== 'visible' || sentRead) return;
  if (++visibleSeconds < 20) return;
  const article = document.querySelector('.article-body');
  if (!article) return;
  const rect = article.getBoundingClientRect();
  if ((innerHeight - rect.top) / Math.max(1, rect.height) >= .5) {
   sentRead = true;
   event('engaged_read');
  }
 }, 1000);
 window.BriefAggregate = {event};
})();
