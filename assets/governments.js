/* Reuse the original cards and story identities in both date filters. */
(function () {
  'use strict';
  const feed = document.getElementById('government-feed');
  if (!feed) return;
  const cards = [...feed.querySelectorAll('[data-story-card]')];
  const buttons = [...document.querySelectorAll('[data-government-view]')];
  const query = new URLSearchParams(location.search);
  const parts = new Intl.DateTimeFormat('en-CA', {timeZone:'Europe/Amsterdam',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());
  const part = name => parts.find(x => x.type === name).value;
  const today = `${part('year')}-${part('month')}-${part('day')}`;
  const sync = document.getElementById('government-sync');
  let checkedToday = false;
  if (sync?.dataset.lastChecked) {
    const checked = new Date(sync.dataset.lastChecked);
    if (!Number.isNaN(checked.getTime())) {
      const checkedParts = new Intl.DateTimeFormat('en-CA', {timeZone:'Europe/Amsterdam',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(checked);
      const checkedPart = name => checkedParts.find(x => x.type === name).value;
      checkedToday = `${checkedPart('year')}-${checkedPart('month')}-${checkedPart('day')}` === today;
      sync.querySelector('time').textContent = new Intl.DateTimeFormat('en-GB', {timeZone:'Europe/Amsterdam',day:'numeric',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit',timeZoneName:'short'}).format(checked);
    }
  }
  const start = new Date(`${today}T00:00:00Z`);
  start.setUTCDate(start.getUTCDate() - 6);
  const firstDay = start.toISOString().slice(0, 10);
  let previous = [];
  try { const saved = JSON.parse(localStorage.getItem('brief-government-reading-order') || '[]'); if (Array.isArray(saved)) previous = saved; } catch (_) {}
  const random = () => crypto.getRandomValues(new Uint32Array(1))[0] / 4294967296;
  const daily = window.BriefGovernmentOrder.shuffle(cards.map(node => ({key:node.dataset.key,node})), previous, random).map(item => item.node);
  try { localStorage.setItem('brief-government-reading-order', JSON.stringify(daily.map(node => node.dataset.key))); } catch (_) {}
  let view = query.get('view') === 'older' ? 'older' : 'day';
  function render(measure = false) {
    const selected = daily.filter(card => view === 'older' ? card.dataset.date < firstDay : card.dataset.date >= firstDay && card.dataset.date <= today);
    for (const card of cards) {
      card.hidden = !selected.includes(card);
      card.querySelector('h3').setAttribute('aria-level', '3');
    }
    const fragment = document.createDocumentFragment();
    const groups = new Map();
    for (const card of daily) {
      const key = card.dataset.date;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(card);
    }
    for (const key of [...groups.keys()].sort((a,b) => b.localeCompare(a))) {
      const section = document.createElement('section');
      section.className = 'government-group';
      section.hidden = !groups.get(key).some(card => !card.hidden);
      const heading = document.createElement('h2');
      heading.className = 'government-group-title';
      heading.textContent = groups.get(key)[0].dataset.displayDate;
      section.append(heading, ...groups.get(key));
      fragment.append(section);
    }
    feed.replaceChildren(fragment);
    buttons.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.governmentView === view)));
    const todayCount = cards.filter(card => card.dataset.date === today).length;
    const latest = checkedToday ? (todayCount ? `${todayCount} Monitor AI announcement${todayCount === 1 ? '' : 's'} dated today as of the last check.` : 'No Monitor AI announcements dated today as of the last check.') : 'Today’s Monitor import has not been checked yet.';
    const browsing = selected.length ? `${selected.length} Monitor AI narrative${selected.length === 1 ? '' : 's'} · ${view === 'day' ? 'last 7 days' : 'older announcements'}` : view === 'day' ? 'No Monitor AI narratives in the last 7 days. Select Older to browse earlier announcements.' : 'No older Monitor AI narratives yet.';
    document.getElementById('government-status').textContent = `${latest} ${browsing}`;
    history.replaceState(null, '', location.pathname + '?' + new URLSearchParams({view}).toString() + location.hash);
    if (measure) window.BriefAnalytics?.event('feed_filter', {kind:'government', market:'all', sort:view});
  }
  buttons.forEach(button => button.addEventListener('click', () => { view = button.dataset.governmentView; render(true); }));
  document.querySelector('[data-government-controls]').hidden = false;
  render();
})();
