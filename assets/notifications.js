'use strict';
// Permission is requested only when a reader presses the enable button.
(async function () {
  const page = document.querySelector('.updates-page');
  if (!page) return;
  const config = JSON.parse(document.getElementById('brief-config').textContent);
  const root = new URL((config.site_url || location.origin) .replace(/\/$/, '') + '/');
  const status = document.getElementById('notification-status');
  const enable = document.getElementById('enable-notifications');
  const disable = document.getElementById('disable-notifications');
  const help = document.getElementById('notification-device-help');
  const tokenKey = 'brief-news-notification-token';
  let registration;
  let subscription;
  const explain = text => { help.textContent = text; help.hidden = false; };
  const showState = active => {
    enable.hidden = active; disable.hidden = !active;
    enable.disabled = false; disable.disabled = false;
  };
  document.getElementById('copy-news-feed').addEventListener('click', async () => {
    const feed = new URL('feed.xml', root).href;
    try {
      await navigator.clipboard.writeText(feed);
      document.getElementById('feed-copy-status').textContent = 'Feed link copied. Paste it into your news reader.';
    } catch (_) {
      document.getElementById('feed-copy-status').textContent = 'Copy this address: ' + feed;
    }
  });
  if (!config.notifications?.enabled || config.is_preview) return;
  const isAppleMobile = /iPhone|iPad|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  if (isAppleMobile && !(navigator.standalone || matchMedia('(display-mode: standalone)').matches)) {
    explain('On iPhone or iPad, use Share → Add to Home Screen. Open the Brief from that icon, then return here to turn on notifications.');
    return;
  }
  if (!isSecureContext || !('serviceWorker' in navigator) || !('PushManager' in window) || !('Notification' in window)) {
    explain('This browser does not support news notifications. You can follow the feed below instead.');
    return;
  }
  const rpc = async (name, body) => {
    const key = config.supabase_publishable_key;
    const headers = {apikey: key, 'Content-Type': 'application/json'};
    if (key.startsWith('eyJ')) headers.Authorization = 'Bearer ' + key;
    const response = await fetch(config.supabase_url + '/rest/v1/rpc/' + name, {method: 'POST', headers, body: JSON.stringify(body)});
    if (!response.ok) throw new Error('Could not save notification preferences. Please try again.');
    return response.json();
  };
  const bytes = encoded => Uint8Array.from(atob(encoded.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4-encoded.length%4)%4)), c => c.charCodeAt(0));
  const token = () => {
    let stored = localStorage.getItem(tokenKey);
    if (!stored) {
      stored = Array.from(crypto.getRandomValues(new Uint8Array(32)), x => x.toString(16).padStart(2, '0')).join('');
      localStorage.setItem(tokenKey, stored);
    }
    return stored;
  };
  const persist = async sub => {
    const data = sub.toJSON();
    const saved = await rpc('brief_push_register', {p_endpoint: data.endpoint, p_p256dh: data.keys.p256dh, p_auth: data.keys.auth, p_token: token()});
    if (!saved) throw new Error('Please turn notifications off and on again on this device.');
  };
  try {
    localStorage.setItem('brief-notification-storage-check', '1');
    localStorage.removeItem('brief-notification-storage-check');
    registration = await navigator.serviceWorker.register(new URL('news-worker.js', root), {scope: root.pathname});
    await navigator.serviceWorker.ready;
    subscription = await registration.pushManager.getSubscription();
    // Local preference storage can be cleared independently of the browser's
    // subscription. Recreate the subscription after an explicit click.
    if (subscription && !localStorage.getItem(tokenKey)) {
      await subscription.unsubscribe(); subscription = null;
    }
    document.getElementById('browser-updates').hidden = false;
    if (subscription) { await persist(subscription); status.textContent = 'Notifications are on for this device.'; }
    showState(Boolean(subscription));
    if (Notification.permission === 'denied') {
      enable.disabled = true;
      status.textContent = 'Notifications are blocked in your browser’s site settings. Allow them there, then reload this page.';
    }
  } catch (_) {
    explain('News notifications could not connect on this device. Try again later, or follow the feed below.');
    return;
  }
  enable.addEventListener('click', async () => {
    enable.disabled = true;
    // The call remains directly inside the user gesture, before network work.
    let permission;
    try { permission = await Notification.requestPermission(); }
    catch (_) { status.textContent = 'Your browser could not request notification permission. Please try again.'; enable.disabled = false; return; }
    if (permission !== 'granted') {
      status.textContent = 'Notifications are off. You can keep reading as usual.';
      enable.disabled = permission === 'denied'; return;
    }
    try {
      subscription = await registration.pushManager.subscribe({userVisibleOnly: true, applicationServerKey: bytes(config.notifications.public_key)});
      await persist(subscription);
      showState(true);
      status.textContent = 'You’re all set. We’ll notify you when the next weekly edition is ready.';
    } catch (_) {
      if (subscription) await subscription.unsubscribe().catch(() => {});
      subscription = null; showState(false);
      status.textContent = 'Notifications were not activated. Please try again later.';
    }
  });
  disable.addEventListener('click', async () => {
    disable.disabled = true;
    try {
      const endpoint = subscription?.endpoint;
      if (subscription) await subscription.unsubscribe();
      if (endpoint) await rpc('brief_push_unsubscribe', {p_endpoint: endpoint, p_token: token()});
      subscription = null; localStorage.removeItem(tokenKey); showState(false);
      status.textContent = 'Notifications are off for this device.';
    } catch (_) {
      disable.disabled = false;
      status.textContent = 'Your browser alerts have been stopped. Please press Turn off again to finish removing the saved preference.';
    }
  });
})();
