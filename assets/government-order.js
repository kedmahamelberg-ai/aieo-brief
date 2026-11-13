/* Weekly reading order. Dates and article identities never change. */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.BriefGovernmentOrder = factory();
})(typeof window === 'object' ? window : this, function () {
  'use strict';
  function monday(day) {
    const date = new Date(day + 'T12:00:00Z');
    date.setUTCDate(date.getUTCDate() - (date.getUTCDay() + 6) % 7);
    return date.toISOString().slice(0, 10);
  }
  function week(items, today) {
    const start = monday(today);
    const current = items.filter(item => item.date >= start && item.date <= today);
    if (current.length) return {items:current, current:true};
    const latest = items.filter(item => item.date <= today).map(item => item.date).sort().at(-1);
    return {items:latest ? items.filter(item => item.date >= monday(latest) && item.date <= latest) : [], current:false};
  }
  function shuffle(items, previous = [], random = Math.random) {
    const result = [...items];
    for (let i = result.length - 1; i > 0; i--) {
      const j = Math.floor(random() * (i + 1));
      [result[i], result[j]] = [result[j], result[i]];
    }
    // Ensure another entrance cannot repeat the same complete order when
    // at least two stories and the previous session order are available.
    if (result.length > 1 && result.length === previous.length && result.every((x,i) => x.key === previous[i])) result.push(result.shift());
    return result;
  }
  return {week, shuffle};
});
