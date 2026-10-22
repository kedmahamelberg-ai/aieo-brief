'use strict';
(function () {
  const community = window.BriefCommunity;
  const consent = () => !!(window.BriefAnalytics?.allowed() && community?.enabled);
  const storageKey = 'brief-public-metric-session';
  const keyPattern = /^(event:[0-9a-f-]{36}|(?:paper|culture):[0-9a-f]{24}|weekly:\d{4}-W\d{2}:(?:markets|research))$/i;
  let session, elapsed = 0, viewDone = false, inFlight = false, retryAt = 0;
  const weeklyReads = new Map();
  function sessionId() {
    if (!consent()) return null;
    try {
      session = sessionStorage.getItem(storageKey);
      if (!/^[0-9a-f-]{36}$/i.test(session || '')) { session = crypto.randomUUID(); sessionStorage.setItem(storageKey, session); }
      return session;
    } catch (_) { session ||= crypto.randomUUID(); return session; }
  }
  function display(metrics) {
    document.querySelectorAll('[data-public-metrics]').forEach(row => {
      const item = metrics?.[row.dataset.publicMetrics];
      let visible = false;
      row.querySelectorAll('[data-metric]').forEach(n => {
        const number = window.BriefCore.publicMetricNumber(item?.[n.dataset.metric]);
        const show = number !== null;
        n.parentElement.hidden = !show;
        n.textContent = show ? new Intl.NumberFormat().format(number) : '';
        visible ||= show;
      });
      row.hidden = !visible;
    });
  }
  async function refresh() {
    if (!community?.enabled || inFlight) return;
    const keys = [...new Set([...document.querySelectorAll('[data-public-metrics]')].map(n => n.dataset.publicMetrics).filter(k => keyPattern.test(k)))];
    if (!keys.length) return;
    inFlight = true;
    try {
      const metrics = await community.metrics(keys);
      window.dispatchEvent(new CustomEvent('brief-metrics', {detail:metrics}));
    }
    catch (_) { /* No placeholder statistics when the service is unavailable. */ }
    finally { inFlight = false; }
  }
  async function record(key, kind) {
    if (!consent() || !keyPattern.test(key || '')) return false;
    await community.rpc('brief_record_engagement', {p_story_key:key,p_session_id:sessionId(),p_kind:kind});
    await refresh(); return true;
  }
  window.BriefEngagement = {share: key => record(key, 'share').catch(() => false),refresh};
  window.addEventListener('brief-metrics', e => display(e.detail));
  window.addEventListener('brief-metrics-refresh', refresh);
  window.addEventListener('brief-auth', refresh);
  window.addEventListener('brief-consent', e => {
    if (!e.detail?.analytics) { elapsed = 0; session = null; viewDone = false; weeklyReads.clear(); try { sessionStorage.removeItem(storageKey); } catch (_) {} }
  });
  document.addEventListener('click', e => {
    const link = e.target.closest?.('#share-dialog a[data-share-channel]');
    if (link) window.BriefEngagement.share(document.getElementById('share-dialog').dataset.storyKey);
  });
  // A view is a visible detail-page visit, never a carousel/card impression.
  setInterval(() => {
    if (!consent() || document.hidden || viewDone || Date.now() < retryAt) return;
    const key = document.body.dataset.storyKey;
    if (!keyPattern.test(key || '')) return;
    elapsed++;
    if (elapsed < 5) return;
    viewDone = true;
    record(key, 'view').catch(() => { viewDone = false; retryAt = Date.now() + 60000; });
  }, 1000);
  // Each detail page contains two readings. Count time only while that reading
  // is visible, and use the same consent and qualification rules as stories.
  setInterval(() => {
    if (!consent() || document.hidden) return;
    document.querySelectorAll('[data-engagement-key]').forEach(node => {
      const key = node.dataset.engagementKey;
      if (!keyPattern.test(key || '')) return;
      const copy = node.querySelector('[data-weekly-reading-body]');
      const rect = copy?.getBoundingClientRect();
      if (!rect || Math.min(rect.bottom, innerHeight) - Math.max(rect.top, 0) < Math.min(160, rect.height * .25)) return;
      const state = weeklyReads.get(key) || {seconds:0,viewDone:false,readDone:false,viewRetryAt:0,readRetryAt:0};
      weeklyReads.set(key, state);
      state.seconds++;
      if (state.seconds >= 5 && !state.viewDone && Date.now() >= state.viewRetryAt) {
        state.viewDone = true;
        record(key, 'view').catch(() => { state.viewDone = false; state.viewRetryAt = Date.now() + 60000; });
      }
      const progress = Math.max(0, Math.min(1, (innerHeight - rect.top) / Math.max(1, rect.height)));
      if (!state.readDone && Date.now() >= state.readRetryAt &&
          window.BriefCore.qualifiedRead(state.seconds, progress, consent())) {
        state.readDone = true;
        community.rpc('brief_community_record_read', {
          p_story_key:key,p_session_id:sessionId(),p_active_seconds:state.seconds,p_progress:progress
        }).then(() => refresh()).catch(() => { state.readDone = false; state.readRetryAt = Date.now() + 60000; });
      }
    });
  }, 1000);
  setInterval(() => { if (!document.hidden) refresh(); }, 60000);
  refresh();
})();
