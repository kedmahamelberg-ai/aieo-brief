(function () {
  'use strict';
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  document.querySelectorAll('[data-carousel]').forEach(root => {
    const slides = [...root.querySelectorAll('[data-carousel-slide]')];
    if (slides.length < 2) return;
    const controls = root.querySelector('[data-carousel-controls]');
    const pause = root.querySelector('[data-carousel-pause]');
    const position = root.querySelector('[data-carousel-position]');
    const status = root.querySelector('[data-carousel-status]');
    let index = 0, timer, stopped = false, hovering = false, visible = true, pointerChoice;
    const show = (next, manual = false) => {
      index = (next + slides.length) % slides.length;
      slides.forEach((slide, i) => { slide.hidden = i !== index; });
      position.textContent = `${index + 1} / ${slides.length}`;
      if (manual) status.textContent = `Showing ${root.dataset.carousel} item ${index + 1} of ${slides.length}`;
    };
    const sync = () => {
      clearInterval(timer);
      const paused = stopped || reduced.matches;
      pause.textContent = paused ? 'Play' : 'Pause';
      pause.setAttribute('aria-label', `${paused ? 'Play' : 'Pause'} ${root.dataset.carousel} rotation`);
      pause.disabled = reduced.matches;
      if (reduced.matches) pause.setAttribute('aria-label', 'Rotation paused by your reduced-motion setting');
      if (!paused && !hovering && visible && !document.hidden) {
        timer = setInterval(() => show(index + 1), root.dataset.carousel === 'culture' ? 8000 : 10000);
      }
    };
    const move = delta => { stopped = true; show(index + delta, true); sync(); };
    controls.hidden = false;
    root.classList.add('carousel-ready');
    show(0);
    // Remember the action shown before pointer focus pauses the carousel.
    pause.addEventListener('pointerdown', () => { pointerChoice = !stopped; });
    pause.addEventListener('pointercancel', () => { pointerChoice = undefined; });
    pause.addEventListener('blur', () => { pointerChoice = undefined; });
    pause.addEventListener('click', event => {
      stopped = event.detail && pointerChoice !== undefined ? pointerChoice : !stopped;
      pointerChoice = undefined;
      sync();
    });
    root.querySelector('[data-carousel-prev]').addEventListener('click', () => move(-1));
    root.querySelector('[data-carousel-next]').addEventListener('click', () => move(1));
    root.addEventListener('mouseenter', () => { hovering = true; sync(); });
    root.addEventListener('mouseleave', () => { hovering = false; sync(); });
    // Focus stops rotation until the reader explicitly presses Play.
    root.addEventListener('focusin', () => { stopped = true; sync(); });
    root.addEventListener('keydown', event => {
      if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
      if (event.target.closest('input,textarea,select')) return;
      event.preventDefault();
      // Keep focus on a stable control when its current slide will be hidden.
      if (event.target.closest('[data-carousel-slide]')) pause.focus();
      move(event.key === 'ArrowLeft' ? -1 : 1);
    });
    document.addEventListener('visibilitychange', sync);
    reduced.addEventListener('change', sync);
    if ('IntersectionObserver' in window) {
      new IntersectionObserver(entries => { visible = entries[0].isIntersecting; sync(); }, {threshold: .15}).observe(root);
    }
    root.querySelectorAll('[data-feature-link]').forEach(link => link.addEventListener('click', () => {
      window.BriefAnalytics?.event('feature_open', {placement: root.dataset.carousel});
    }));
    sync();
  });
})();
