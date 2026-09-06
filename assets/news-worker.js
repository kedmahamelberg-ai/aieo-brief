'use strict';
// No page caching: editions always come from the current website.
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));
self.addEventListener('push', event => {
  let payload;
  try { payload = event.data.json(); } catch (_) { return; }
  const root = new URL(self.registration.scope);
  let target = root.href;
  try {
    const candidate = new URL(payload.url, root);
    if (candidate.origin === root.origin && candidate.pathname.startsWith(root.pathname)) target = candidate.href;
  } catch (_) {}
  event.waitUntil(self.registration.showNotification(String(payload.title || 'The Brief').slice(0, 100), {
    body: String(payload.body || 'A new AI news edition is ready.').slice(0, 220),
    icon: new URL('assets/notification-icon.svg', root).href,
    tag: String(payload.tag || 'brief-news').slice(0, 80),
    renotify: false,
    data: {url: target}
  }));
});
self.addEventListener('notificationclick', event => {
  event.notification.close();
  const root = new URL(self.registration.scope);
  const candidate = new URL(event.notification.data?.url || root.href, root);
  const target = candidate.origin === root.origin && candidate.pathname.startsWith(root.pathname) ? candidate.href : root.href;
  event.waitUntil(self.clients.matchAll({type: 'window', includeUncontrolled: true}).then(async windows => {
    for (const window of windows) {
      if (window.url === target && 'focus' in window) return window.focus();
    }
    return self.clients.openWindow(target);
  }));
});
