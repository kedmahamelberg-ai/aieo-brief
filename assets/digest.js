'use strict';
(function () {
  const list = document.getElementById('digest-items');
  if (!list) return;
  const items = new Map(JSON.parse(document.getElementById('brief-items').textContent).map(i => [i.key,i]));
  const config = JSON.parse(document.getElementById('brief-config').textContent);
  const keys = [...new Set((new URLSearchParams(location.search).get('items') || '').split(','))].slice(0,3);
  for (const key of keys) {
    const item = items.get(key);
    if (!item || !/^(story|research|culture)\/[a-zA-Z0-9_-]+\/index\.html$/.test(item.path || '')) continue;
    const article = document.createElement('article'); article.className = 'feed-story';
    const kind = document.createElement('p'); kind.className = 'eyebrow'; kind.textContent = {news:'AI newspaper',research:'AI research',culture:'A daily pause'}[item.kind] || '';
    const h = document.createElement('h2'), a = document.createElement('a');
    a.href = new URL(item.path, config.site_url.replace(/\/$/,'') + '/').href; a.textContent = item.headline; h.append(a);
    const p = document.createElement('p'); p.textContent = item.deck || '';
    article.append(kind,h,p); list.append(article);
  }
  if (!list.children.length) list.textContent = 'This selection is no longer available. Explore today’s Brief using the link below.';
})();
