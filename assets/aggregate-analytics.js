/* Aggregate audience counts: no cookies, storage, visitor IDs or account tokens. */
(function () {
 'use strict';
 const config = JSON.parse(document.getElementById('brief-config').textContent);
 const events = new Set(['page_view','engaged_read','source_open','share_option','save','unsave','like','unlike','support_link']);
 const path = location.pathname;
 function deviceClass(nav) {
  const ua = nav.userAgent || '';
  if (/bot|spider|crawler|headless/i.test(ua)) return 'other';
  if (/iPad|Tablet|Kindle|Silk|PlayBook/i.test(ua) || (/Macintosh/i.test(ua) && nav.maxTouchPoints > 1) || (/Android/i.test(ua) && !/Mobile/i.test(ua))) return 'tablet';
  if (nav.userAgentData?.mobile || /Mobi|iPhone|iPod|Android|Windows Phone/i.test(ua)) return 'mobile';
  if (/Windows|Macintosh|Linux|CrOS|X11/i.test(ua)) return 'desktop';
  return 'other';
 }
 const device = deviceClass(navigator);
 const active = !config.is_preview && config.supabase_url && config.supabase_publishable_key && /^\/(?:[a-z0-9-]+\/)*$/.test(path) && !/bot|spider|crawler|headless/i.test(navigator.userAgent || '');
 let sentView = false, sentRead = false, visibleSeconds = 0;
 function event(name) {
  if (!active || !events.has(name)) return;
  // Exclude queries, fragments, referrers, raw user agents and auth sessions.
  fetch(config.supabase_url + '/rest/v1/rpc/brief_record_aggregate', {
   method:'POST', credentials:'omit', referrerPolicy:'no-referrer', keepalive:true,
   headers:{apikey:config.supabase_publishable_key,'Content-Type':'application/json'},
   body:JSON.stringify({p_path:path,p_device:device,p_event:name})
  }).catch(() => {});
 }
 function view() { if (!sentView && document.visibilityState === 'visible') { sentView = true; event('page_view'); } }
 view(); document.addEventListener('visibilitychange', view);
 if (active && document.body.dataset.storyKey) setInterval(() => {
  if (document.visibilityState !== 'visible' || sentRead) return;
  if (++visibleSeconds < 20) return;
  const article = document.querySelector('.article-body'); if (!article) return;
  const rect = article.getBoundingClientRect();
  if ((innerHeight - rect.top) / Math.max(1, rect.height) >= .5) { sentRead = true; event('engaged_read'); }
 },1000);
 window.BriefAggregate = {event,deviceClass};
})();
