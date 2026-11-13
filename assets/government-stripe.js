/* A new reading order on each visit. Every link opens Governments say. */
(function () {
  'use strict';
  const run = document.getElementById('government-stripe-items');
  const repeat = document.getElementById('government-stripe-repeat');
  const track = document.getElementById('government-stripe-track');
  if (!run || !repeat || !track || !window.BriefGovernmentOrder) return;
  const links = [...run.querySelectorAll('a[data-key]')];
  const parts = new Intl.DateTimeFormat('en-CA', {timeZone:'Europe/Amsterdam',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());
  const part = name => parts.find(x => x.type === name).value;
  const today = `${part('year')}-${part('month')}-${part('day')}`;
  const weekly = window.BriefGovernmentOrder.week(links.map(node => ({key:node.dataset.key,date:node.dataset.date,node})), today);
  let previous = [];
  try { const saved = JSON.parse(localStorage.getItem('brief-government-stripe-order') || '[]'); if (Array.isArray(saved)) previous = saved; } catch (_) {}
  const random = () => crypto.getRandomValues(new Uint32Array(1))[0] / 4294967296;
  const selected = window.BriefGovernmentOrder.shuffle(weekly.items, previous, random);
  run.replaceChildren(...selected.map(item => item.node));
  try { localStorage.setItem('brief-government-stripe-order', JSON.stringify(selected.map(item => item.key))); } catch (_) {}
  repeat.replaceChildren(...selected.map(item => {
    const copy = item.node.cloneNode(true);
    copy.tabIndex = -1;
    return copy;
  }));
  if (selected.length > 1) {
    track.style.setProperty('--stripe-duration', `${Math.max(70, selected.length * 14)}s`);
    track.dataset.ready = 'true';
  }
})();
