/* One calm announcement at a time; a new order on each visit. */
(function () {
  'use strict';
  const stripe = document.querySelector('.government-stripe');
  const run = document.getElementById('government-stripe-items');
  const controls = document.getElementById('government-stripe-controls');
  const position = document.getElementById('government-stripe-position');
  const next = document.getElementById('government-stripe-next');
  const pause = document.getElementById('government-stripe-pause');
  if (!stripe || !run || !controls || !position || !next || !pause || !window.BriefGovernmentOrder) return;

  const links = [...run.querySelectorAll('a[data-key]')];
  const parts = new Intl.DateTimeFormat('en-CA', {timeZone:'Europe/Amsterdam',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());
  const part = name => parts.find(x => x.type === name).value;
  const today = `${part('year')}-${part('month')}-${part('day')}`;
  const weekly = window.BriefGovernmentOrder.week(links.map(node => ({key:node.dataset.key,date:node.dataset.date,node})), today);
  let previous = [];
  try { const saved = JSON.parse(localStorage.getItem('brief-government-stripe-order') || '[]'); if (Array.isArray(saved)) previous = saved; } catch (_) {}
  const random = () => crypto.getRandomValues(new Uint32Array(1))[0] / 4294967296;
  const selected = window.BriefGovernmentOrder.shuffle(weekly.items, previous, random);
  if (!selected.length) { stripe.hidden = true; return; }
  run.replaceChildren(...selected.map(item => item.node));
  try { localStorage.setItem('brief-government-stripe-order', JSON.stringify(selected.map(item => item.key))); } catch (_) {}

  const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const hoverCapable = window.matchMedia('(hover: hover)');
  let index = 0;
  let timer;
  let paused = false;
  let focusWithin = false;
  let playWhileFocused = false;
  try { paused = localStorage.getItem('brief-government-stripe-paused') === 'true'; } catch (_) {}

  function show(nextIndex, animate) {
    index = nextIndex;
    selected.forEach((item, i) => {
      item.node.classList.remove('is-entering');
      item.node.hidden = i !== index;
    });
    const active = selected[index].node;
    if (animate && !motion.matches) active.classList.add('is-entering');
    position.textContent = `${index + 1} / ${selected.length}`;
  }
  function stop() { clearTimeout(timer); timer = undefined; }
  function canPlay() {
    return selected.length > 1 && !paused && !motion.matches && !document.hidden &&
      !(hoverCapable.matches && stripe.matches(':hover')) && (!focusWithin || playWhileFocused);
  }
  function schedule() {
    stop();
    if (canPlay()) timer = setTimeout(() => {
      show((index + 1) % selected.length, true);
      schedule();
    }, 12000);
  }
  function syncControls() {
    pause.hidden = motion.matches;
    pause.textContent = paused ? 'Play' : 'Pause';
    pause.setAttribute('aria-label', paused ? 'Play automatic announcements' : 'Pause automatic announcements');
    schedule();
  }

  show(0, false);
  if (selected.length === 1) return;
  controls.hidden = false;
  next.addEventListener('click', () => { show((index + 1) % selected.length, true); playWhileFocused = true; schedule(); });
  pause.addEventListener('click', () => {
    paused = !paused;
    playWhileFocused = !paused;
    try { localStorage.setItem('brief-government-stripe-paused', String(paused)); } catch (_) {}
    syncControls();
  });
  stripe.addEventListener('mouseenter', stop);
  stripe.addEventListener('mouseleave', schedule);
  stripe.addEventListener('focusin', () => { focusWithin = true; playWhileFocused = false; stop(); });
  stripe.addEventListener('focusout', event => {
    if (!stripe.contains(event.relatedTarget)) { focusWithin = false; playWhileFocused = false; schedule(); }
  });
  document.addEventListener('visibilitychange', schedule);
  motion.addEventListener('change', syncControls);
  syncControls();
})();
