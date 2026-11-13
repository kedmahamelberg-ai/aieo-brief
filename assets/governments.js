/* Reuse the same cards and story identities in both views. */
(function () {
  'use strict';
  const feed = document.getElementById('government-feed');
  if (!feed) return;
  const cards = [...feed.querySelectorAll('[data-story-card]')];
  const day = document.getElementById('government-day');
  const country = document.getElementById('government-country');
  const buttons = [...document.querySelectorAll('[data-government-view]')];
  const query = new URLSearchParams(location.search);
  let view = query.get('view') === 'country' ? 'country' : 'day';
  if ([...country.options].some(x => x.value === query.get('country'))) country.value = query.get('country');
  if ([...day.options].some(x => x.value === query.get('day'))) day.value = query.get('day');
  function render(measure = false) {
    const selected = cards.filter(card => view === 'day' ? day.value === 'all' || card.dataset.date === day.value : country.value === 'all' || card.dataset.country === country.value);
    const groups = new Map();
    for (const card of cards) {
      card.hidden = !selected.includes(card);
      const key = view === 'day' ? card.dataset.date : card.dataset.countryName;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(card);
    }
    const fragment = document.createDocumentFragment();
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
    document.querySelector('[data-day-control]').hidden = view !== 'day';
    document.querySelector('[data-country-control]').hidden = view !== 'country';
    buttons.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.governmentView === view)));
    document.getElementById('government-status').textContent = selected.length ? `${selected.length} AI announcement${selected.length === 1 ? '' : 's'} · ${view === 'day' ? 'by publication day' : 'by issuing country'}` : 'No checked AI announcements for this selection.';
    const params = new URLSearchParams({view});
    params.set(view === 'day' ? 'day' : 'country', view === 'day' ? day.value : country.value);
    history.replaceState(null, '', location.pathname + '?' + params.toString() + location.hash);
    if (measure) window.BriefAnalytics?.event('feed_filter', {kind:'government', market:view === 'country' ? country.value : 'all', sort:view});
  }
  buttons.forEach(button => button.addEventListener('click', () => { view = button.dataset.governmentView; render(true); }));
  day.addEventListener('change', () => render(true));
  country.addEventListener('change', () => render(true));
  document.querySelector('[data-government-controls]').hidden = false;
  render();
})();
