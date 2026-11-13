/* Reuse the same cards and story identities in both views. */
(function () {
  'use strict';
  const feed = document.getElementById('government-feed');
  if (!feed) return;
  const cards = [...feed.querySelectorAll('[data-story-card]')];
  const country = document.getElementById('government-country');
  const buttons = [...document.querySelectorAll('[data-government-view]')];
  const query = new URLSearchParams(location.search);
  const parts = new Intl.DateTimeFormat('en-CA', {timeZone:'Europe/Amsterdam',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());
  const part = name => parts.find(x => x.type === name).value;
  const today = `${part('year')}-${part('month')}-${part('day')}`;
  const weekly = window.BriefGovernmentOrder.week(cards.map(node => ({key:node.dataset.key,date:node.dataset.date,node})), today);
  let previous = [];
  try { const saved = JSON.parse(localStorage.getItem('brief-government-reading-order') || '[]'); if (Array.isArray(saved)) previous = saved; } catch (_) {}
  const random = () => crypto.getRandomValues(new Uint32Array(1))[0] / 4294967296;
  const daily = window.BriefGovernmentOrder.shuffle(weekly.items, previous, random).map(item => item.node);
  try { localStorage.setItem('brief-government-reading-order', JSON.stringify(daily.map(node => node.dataset.key))); } catch (_) {}
  let view = query.get('view') === 'country' ? 'country' : 'day';
  if ([...country.options].some(x => x.value === query.get('country'))) country.value = query.get('country');
  function render(measure = false) {
    const selected = view === 'day' ? daily : cards.filter(card => country.value === 'all' || card.dataset.country === country.value);
    for (const card of cards) {
      card.hidden = !selected.includes(card);
      card.querySelector('h3').setAttribute('aria-level', view === 'day' ? '2' : '3');
    }
    const fragment = document.createDocumentFragment();
    if (view === 'day') {
      fragment.append(...daily, ...cards.filter(card => !daily.includes(card)));
    } else {
      const groups = new Map();
      for (const card of cards) {
        if (!groups.has(card.dataset.countryName)) groups.set(card.dataset.countryName, []);
        groups.get(card.dataset.countryName).push(card);
      }
      for (const key of [...groups.keys()].sort((a,b) => a.localeCompare(b))) {
        const section = document.createElement('section');
        section.className = 'government-group';
        section.hidden = !groups.get(key).some(card => !card.hidden);
        const heading = document.createElement('h2');
        heading.className = 'government-group-title';
        heading.textContent = key;
        section.append(heading, ...groups.get(key));
        fragment.append(section);
      }
    }
    feed.replaceChildren(fragment);
    document.querySelector('[data-country-control]').hidden = view !== 'country';
    buttons.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.governmentView === view)));
    document.getElementById('government-status').textContent = selected.length ? `${selected.length} AI announcement${selected.length === 1 ? '' : 's'} · ${view === 'day' ? weekly.current ? 'this week' : 'latest available week' : 'by issuing country'}` : 'No checked AI announcements for this selection.';
    const params = new URLSearchParams({view});
    if (view === 'country') params.set('country', country.value);
    history.replaceState(null, '', location.pathname + '?' + params.toString() + location.hash);
    if (measure) window.BriefAnalytics?.event('feed_filter', {kind:'government', market:view === 'country' ? country.value : 'all', sort:view});
  }
  buttons.forEach(button => button.addEventListener('click', () => { view = button.dataset.governmentView; render(true); }));
  country.addEventListener('change', () => render(true));
  document.querySelector('[data-government-controls]').hidden = false;
  render();
})();
