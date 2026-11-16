/* Reuse the same cards and story identities in both views. */
(function () {
  'use strict';
  const feed = document.getElementById('government-feed');
  if (!feed) return;
  const cards = [...feed.querySelectorAll('[data-story-card]')];
  const country = document.getElementById('government-country');
  const buttons = [...document.querySelectorAll('[data-government-view]')];
  const query = new URLSearchParams(location.search);
  let previous = [];
  try { const saved = JSON.parse(localStorage.getItem('brief-government-reading-order') || '[]'); if (Array.isArray(saved)) previous = saved; } catch (_) {}
  const random = () => crypto.getRandomValues(new Uint32Array(1))[0] / 4294967296;
  const daily = window.BriefGovernmentOrder.shuffle(cards.map(node => ({key:node.dataset.key,node})), previous, random).map(item => item.node);
  try { localStorage.setItem('brief-government-reading-order', JSON.stringify(daily.map(node => node.dataset.key))); } catch (_) {}
  let view = query.get('view') === 'country' ? 'country' : 'day';
  if ([...country.options].some(x => x.value === query.get('country'))) country.value = query.get('country');
  function render(measure = false) {
    const selected = view === 'day' ? daily : cards.filter(card => country.value === 'all' || card.dataset.country === country.value);
    for (const card of cards) {
      card.hidden = !selected.includes(card);
      card.querySelector('h3').setAttribute('aria-level', '3');
    }
    const fragment = document.createDocumentFragment();
    const groups = new Map();
    for (const card of view === 'day' ? daily : cards) {
      const key = view === 'day' ? card.dataset.date : card.dataset.countryName;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(card);
    }
    const keys = [...groups.keys()].sort((a,b) => view === 'day' ? b.localeCompare(a) : a.localeCompare(b));
    for (const key of keys) {
      const section = document.createElement('section');
      section.className = 'government-group';
      section.hidden = !groups.get(key).some(card => !card.hidden);
      const heading = document.createElement('h2');
      heading.className = 'government-group-title';
      heading.textContent = view === 'day' ? groups.get(key)[0].dataset.displayDate : key;
      section.append(heading, ...groups.get(key));
      fragment.append(section);
    }
    feed.replaceChildren(fragment);
    document.querySelector('[data-country-control]').hidden = view !== 'country';
    buttons.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.governmentView === view)));
    document.getElementById('government-status').textContent = selected.length ? `${selected.length} Monitor AI narrative${selected.length === 1 ? '' : 's'} · ${view === 'day' ? 'all published dates' : 'by issuing country'}` : 'No Monitor AI narratives for this selection.';
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
