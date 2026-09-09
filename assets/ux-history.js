/* Private, consent-linked UX history. Never sends emails, comment bodies,
   search words, raw IP addresses, URLs, or raw user-agent strings. */
(function () {
  'use strict';
  const config = JSON.parse(document.getElementById('brief-config').textContent);
  const items = JSON.parse(document.getElementById('brief-items').textContent);
  const byKey = new Map(items.map(x => [x.key, x]));
  const accessKey = 'brief-ux-access-v1', sessionKey = 'brief-ux-session-v1';
  const enabled = !config.is_preview && !!config.supabase_url && !!config.supabase_publishable_key;
  const names = new Set(('page_view item_impression story_open like unlike save unsave comment_submitted comment_deleted share_option source_open feed_filter feed_sort search_used show_more active_reading qualified_read scroll_depth carousel_control feature_open notification_open notification_enabled notification_disabled notification_failed sign_in_requested sign_in_failed sign_in_succeeded sign_out support_link sponsor_click ad_placement_visible media_play media_pause media_ended privacy_open').split(' '));
  const numeric = new Set(('seconds progress position result_count query_length shown_views shown_likes shown_comments shown_shares shown_saves shown_reads sequence').split(' '));
  const textual = new Set(('channel kind market sort placement topic direction state layout_version release_id content_hash measurement').split(' '));
  let token = null, session = null, active = false, queue = [], flushing = false, sequence = 0;
  let epoch = 0, state = 'off', operation = Promise.resolve(), observer = null;
  let activeSeconds = 0, progress = 0, lastInteraction = Date.now(), readSent = false;
  const depths = new Set(), observed = new Set(), nodeIds = new WeakMap(); let nodeCounter = 0;
  function store(key, value, where = localStorage) { try { value ? where.setItem(key, value) : where.removeItem(key); } catch (_) {} }
  function read(key, where = localStorage) { try { return where.getItem(key); } catch (_) { return null; } }
  async function rpc(name, body, keepalive = false) {
    const headers = {'Content-Type': 'application/json', apikey: config.supabase_publishable_key};
    if (config.supabase_publishable_key.startsWith('eyJ')) headers.Authorization = 'Bearer ' + config.supabase_publishable_key;
    const response = await fetch(config.supabase_url.replace(/\/$/, '') + '/rest/v1/rpc/' + name, {
      method: 'POST', headers, body: JSON.stringify(body), credentials: 'omit', referrerPolicy: 'no-referrer', keepalive
    });
    if (!response.ok) throw new Error('UX storage is temporarily unavailable.');
    return response.json();
  }
  function announce() {
    const node = document.getElementById('ux-storage-status');
    if (node) node.textContent = state === 'ready' ? 'Your measurement choices are connected.' :
      state === 'error' ? 'The database could not be reached. No activity is being sent. Please retry your privacy choice.' : '';
  }
  function clean(props = {}) {
    const output = {};
    for (const [key, value] of Object.entries(props)) {
      if (numeric.has(key) && typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1e9) output[key] = value;
      if (textual.has(key) && typeof value === 'string' && /^[A-Za-z0-9_:. /-]{0,100}$/.test(value)) output[key] = value;
    }
    return output;
  }
  function track(name, props = {}) {
    if (!active || !token || !names.has(name)) return false;
    const key = props.story_key || document.body.dataset.storyKey || '';
    if (key && !byKey.has(key)) return false;
    const item = byKey.get(key);
    const properties = clean({...props, layout_version: config.layout_version || 'brief-unknown',
      release_id: item?.edition || config.release_id || '', content_hash: item?.content_hash,
      kind: props.kind || item?.kind, sequence: ++sequence});
    queue.push({id: crypto.randomUUID(), name, occurred_at: new Date().toISOString(), session_id: session,
      story_key: key || null, page_type: document.body.dataset.page || 'home',
      device_class: innerWidth < 640 ? 'small' : innerWidth < 1024 ? 'medium' : 'large', properties});
    if (queue.length > 100) queue.shift();
    if (queue.length >= 20) flush();
    return true;
  }
  async function flush(keepalive = false) {
    if (!active || !token || !queue.length || flushing) return;
    flushing = true;
    const batch = queue.splice(0, 25), current = epoch, usedToken = token;
    try { await rpc('brief_ux_record', {p_token: usedToken, p_events: batch}, keepalive); }
    catch (_) { if (active && epoch === current) queue = batch.concat(queue).slice(0, 100); }
    finally { flushing = false; }
  }
  function resetObservation() { observer?.disconnect(); observer = null; observed.clear(); depths.clear(); activeSeconds = 0; progress = 0; readSent = false; }
  function start(analytics, research) {
    const current = ++epoch;
    active = false; queue = []; resetObservation();
    if (!enabled) return Promise.resolve();
    operation = operation.catch(() => {}).then(async () => {
      const previous = read(accessKey);
      if (!analytics && !research && !previous) { state = 'off'; announce(); return; }
      try {
        state = 'connecting';
        const result = await rpc('brief_ux_consent', {p_analytics: !!analytics, p_research: !!research, p_token: previous});
        store(accessKey, result.token);
        if (current !== epoch) return;
        token = result.token;
        active = !!token && (analytics || research);
        if (active) {
          session = read(sessionKey, sessionStorage);
          if (!/^[0-9a-f-]{36}$/i.test(session || '')) session = crypto.randomUUID();
          store(sessionKey, session, sessionStorage);
          state = 'ready'; track('page_view'); observe();
        } else { state = 'off'; store(sessionKey, null, sessionStorage); }
      } catch (_) { if (current === epoch) { state = 'error'; active = false; } }
      announce();
    });
    return operation;
  }
  async function erase() {
    active = false; queue = []; ++epoch; resetObservation();
    await operation.catch(() => {});
    const previous = read(accessKey);
    if (previous) await rpc('brief_ux_erase', {p_token: previous});
    token = null; store(accessKey, null); store(sessionKey, null, sessionStorage); state = 'off'; announce();
  }
  function keyFor(node) {
    if (node.dataset.key) return node.dataset.key;
    const row = node.querySelector('[data-public-metrics]');
    if (row) return row.dataset.publicMetrics;
    const link = node.matches('a[href]') ? node : node.querySelector('a[href]');
    if (!link) return null;
    const url = new URL(link.href, location.href);
    if (url.origin !== location.origin) return null;
    const path = url.pathname.replace(/index\.html$/, '');
    return items.find(x => path.endsWith('/' + x.path.replace(/index\.html$/, '')))?.key || null;
  }
  function visible(node) { return !document.hidden && !node.closest('[hidden]') && node.getClientRects().length > 0; }
  function observe() {
    if (!('IntersectionObserver' in window) || !active) return;
    observer = new IntersectionObserver(entries => {
      for (const entry of entries) {
        const node = entry.target, key = keyFor(node);
        if (!nodeIds.has(node)) nodeIds.set(node, ++nodeCounter);
        const stamp = (key || '') + ':' + nodeIds.get(node);
        if (!entry.isIntersecting || entry.intersectionRatio < .5 || observed.has(stamp)) continue;
        const current = epoch;
        setTimeout(() => {
          if (!active || current !== epoch || observed.has(stamp) || !visible(node)) return;
          const rect = node.getBoundingClientRect();
          if (Math.min(rect.bottom, innerHeight) - Math.max(rect.top, 0) < rect.height * .5) return;
          if (node.classList.contains('advertisement')) {
            if (node.querySelector('ins[data-ad-status="filled"]')) {
              observed.add(stamp); track('ad_placement_visible', {placement: node.dataset.adKind, measurement: 'first_party_visibility_not_google_impression'});
            }
            return;
          }
          if (!key) return;
          const counts = {};
          node.querySelectorAll('[data-metric]').forEach(n => {
            if (/^[\d, .]+$/.test(n.textContent.trim())) counts['shown_' + n.dataset.metric] = Number(n.textContent.replace(/\D/g, ''));
          });
          observed.add(stamp);
          const position = [...document.querySelectorAll('[data-story-card]')].filter(visible).indexOf(node) + 1;
          track('item_impression', {story_key: key, position,
            placement: node.closest('[data-carousel]')?.dataset.carousel || (node.classList.contains('lead-story') ? 'lead' : 'feed'), ...counts});
        }, 1000);
      }
    }, {threshold: .5});
    document.querySelectorAll('[data-story-card],.lead-story,[data-carousel-slide],.advertisement').forEach(node => observer.observe(node));
  }
  let searchTimer;
  document.addEventListener('input', e => {
    if (e.target.id !== 'story-search') return;
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => track('search_used', {query_length: e.target.value.length,
      result_count: [...document.querySelectorAll('[data-story-card]')].filter(visible).length}), 650);
  });
  document.addEventListener('click', e => {
    lastInteraction = Date.now();
    const target = e.target.closest?.('a,button'); if (!target) return;
    if (target.matches('a[href]')) {
      const key = keyFor(target); if (key) track('story_open', {story_key: key});
      if (target.classList.contains('notification-cta')) track('notification_open');
    }
    if (target.id === 'show-more-stories') track('show_more');
    if (target.dataset.action === 'privacy') track('privacy_open');
    if (target.matches('[data-carousel-prev],[data-carousel-next],[data-carousel-pause]')) track('carousel_control', {
      placement: target.closest('[data-carousel]')?.dataset.carousel,
      state: target.hasAttribute('data-carousel-prev') ? 'previous' : target.hasAttribute('data-carousel-next') ? 'next' : 'pause_toggle'});
  });
  document.addEventListener('change', e => {
    if (['topic-filter','direction-filter'].includes(e.target.id)) track('feed_filter', {[e.target.id === 'topic-filter' ? 'topic' : 'direction']: e.target.value});
  });
  ['pointermove','keydown','scroll','touchstart'].forEach(name => addEventListener(name, () => { lastInteraction = Date.now(); }, {passive:true}));
  setInterval(() => {
    if (!active || document.hidden || Date.now() - lastInteraction > 60000) return;
    const article = document.getElementById('article-content'); if (!article) return;
    activeSeconds++;
    const rect = article.getBoundingClientRect(); progress = Math.max(progress, Math.max(0, Math.min(1, (innerHeight - rect.top) / rect.height)));
    for (const threshold of [.25,.5,.75,1]) if (progress >= threshold && !depths.has(threshold)) {
      depths.add(threshold); track('scroll_depth', {progress: threshold, seconds: activeSeconds});
    }
    if (!readSent && activeSeconds >= 20 && progress >= .5) { readSent = true; track('qualified_read', {seconds: activeSeconds, progress}); }
    if (activeSeconds % 30 === 0) track('active_reading', {seconds: activeSeconds, progress});
  }, 1000);
  document.addEventListener('visibilitychange', () => { if (document.hidden) { if (activeSeconds) track('active_reading', {seconds:activeSeconds, progress}); flush(true); } });
  addEventListener('pagehide', () => flush(true));
  const audio = document.getElementById('culture-audio');
  for (const event of ['play','pause','ended']) audio?.addEventListener(event, () => track('media_' + event, {seconds: Math.round(audio.currentTime)}));
  setInterval(() => flush(), 10000);
  window.BriefUX = {start,track,erase,flush,status:() => state,clean};
})();
