'use strict';
(function () {
  const community = window.BriefCommunity;
  const consent = () => !!(window.BriefAnalytics?.allowed() && community?.enabled);
  const storageKey = 'brief-public-metric-session';
  const keyPattern = /^(event:[0-9a-f-]{36}|(?:paper|culture):[0-9a-f]{24})$/i;
  let session, elapsed = 0, viewDone = false, inFlight = false, retryAt = 0;
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
      row.querySelectorAll('[data-metric]').forEach(n => {
        const number = item?.[n.dataset.metric];
        n.textContent = typeof number === 'number' && Number.isFinite(number) && number >= 0 ? new Intl.NumberFormat().format(number) : '—';
      });
    });
  }
  async function refresh() {
    if (!community?.enabled || inFlight) return;
    const keys = [...new Set([...document.querySelectorAll('[data-public-metrics]')].map(n => n.dataset.publicMetrics).filter(k => keyPattern.test(k)))];
    if (!keys.length) return;
    inFlight = true;
    try { display(await community.metrics(keys)); }
    catch (_) { /* An unavailable count remains a dash, not a fabricated zero. */ }
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
    if (!e.detail?.analytics) { elapsed = 0; session = null; viewDone = false; try { sessionStorage.removeItem(storageKey); } catch (_) {} }
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
  setInterval(() => { if (!document.hidden) refresh(); }, 60000);
  refresh();
})();
