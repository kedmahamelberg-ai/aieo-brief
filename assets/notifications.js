'use strict';
// Browser permission and topic consent are separate, explicit reader actions.
(async function () {
  if (!document.querySelector('.updates-page')) return;
  const config = JSON.parse(document.getElementById('brief-config').textContent);
  const root = new URL((config.site_url || location.origin).replace(/\/$/, '') + '/');
  const status = document.getElementById('notification-status');
  const enable = document.getElementById('enable-notifications');
  const save = document.getElementById('save-notification-preferences');
  const disable = document.getElementById('disable-notifications');
  const help = document.getElementById('notification-device-help');
  const tokenKey = 'brief-news-notification-token';
  const boxes = [...document.querySelectorAll('[name="notification-topic"]')];
  let registration, subscription;
  const explain = text => { help.textContent = text; help.hidden = false; };
  const showState = active => {
    enable.hidden = active; save.hidden = !active; disable.hidden = !active;
    enable.disabled = false; save.disabled = false; disable.disabled = false;
  };
  const topics = () => boxes.filter(x => x.checked).map(x => x.value);
  document.getElementById('copy-news-feed').addEventListener('click', async () => {
    const feed = new URL('feed.xml', root).href;
    try { await navigator.clipboard.writeText(feed); document.getElementById('feed-copy-status').textContent = 'Feed link copied.'; }
    catch (_) { document.getElementById('feed-copy-status').textContent = 'Copy this address: ' + feed; }
  });
  if (!config.notifications?.enabled || config.is_preview) {
    status.textContent = config.is_preview ? 'This preview does not send notifications.' : 'Browser updates are being connected. Please check back shortly.';
    return;
  }
  const isAppleMobile = /iPhone|iPad|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  if (isAppleMobile && !(navigator.standalone || matchMedia('(display-mode: standalone)').matches)) {
    status.textContent = 'Add the Brief to your Home Screen to enable updates.';
    explain('On iPhone or iPad, use Share → Add to Home Screen. Open that icon, then choose your updates here.'); return;
  }
  if (!isSecureContext || !('serviceWorker' in navigator) || !('PushManager' in window) || !('Notification' in window)) {
    status.textContent = 'This browser does not support notifications. The news feed below is available instead.'; return;
  }
  const rpc = async (name, body) => {
    const key = config.supabase_publishable_key;
    const headers = {apikey: key, 'Content-Type': 'application/json'};
    if (key.startsWith('eyJ')) headers.Authorization = 'Bearer ' + key;
    const response = await fetch(config.supabase_url + '/rest/v1/rpc/' + name, {method: 'POST', headers, body: JSON.stringify(body), credentials:'omit', referrerPolicy:'no-referrer'});
    if (!response.ok) throw new Error('Preferences could not be saved. Please try again shortly.');
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
  const persist = async () => {
    const selected = topics();
    if (!selected.length) throw new Error('Choose at least one category, or use Turn off updates.');
    const data = subscription.toJSON();
    const saved = await rpc('brief_push_register_v2', {p_endpoint:data.endpoint, p_p256dh:data.keys.p256dh, p_auth:data.keys.auth, p_token:token(), p_topics:selected});
    if (!saved) throw new Error('Turn off updates, then enable them again on this device.');
  };
  try {
    localStorage.setItem('brief-notification-storage-check', '1'); localStorage.removeItem('brief-notification-storage-check');
    registration = await navigator.serviceWorker.register(new URL('news-worker.js', root), {scope:root.pathname});
    await navigator.serviceWorker.ready;
    subscription = await registration.pushManager.getSubscription();
    if (subscription && !localStorage.getItem(tokenKey)) {
      // Lost capability: do not take ownership of another saved subscription.
      await subscription.unsubscribe(); subscription = null;
    }
    showState(Boolean(subscription));
    if (subscription) {
      const prefs = await rpc('brief_push_preferences', {p_endpoint:subscription.endpoint,p_token:token()});
      if (prefs?.topics) boxes.forEach(b => { b.checked = prefs.topics.includes(b.value); });
      status.textContent = prefs?.consent_version === 'twice-daily-v2'
        ? 'Updates are on. Change any choices and press Save my choices.'
        : 'Your earlier weekly setting has not been switched automatically. Save your choices to receive up to two updates a day.';
    } else status.textContent = 'Choose your interests, then press Notify me.';
    if (Notification.permission === 'denied') { enable.disabled = true; status.textContent = 'Notifications are blocked in your browser’s site settings. Allow them there, then reload this page.'; }
  } catch (_) { status.textContent = 'Updates could not connect. Please try again later.'; return; }
  enable.addEventListener('click', async () => {
    if (!topics().length) { status.textContent = 'Choose at least one category first.'; return; }
    enable.disabled = true;
    let permission;
    // Keep permission request inside the click, before asynchronous network work.
    try { permission = await Notification.requestPermission(); }
    catch (_) { status.textContent = 'Your browser could not request permission.'; enable.disabled = false; return; }
    if (permission !== 'granted') { status.textContent = 'Updates remain off. Keep reading as usual.'; enable.disabled = permission === 'denied'; return; }
    try {
      subscription = await registration.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:bytes(config.notifications.public_key)});
      await persist(); window.BriefUX?.track('notification_enabled',{state:topics().sort().join('_')}); showState(true); status.textContent = 'You’re all set. Your chosen topics, in up to two browser updates a day.';
    } catch (e) {
      if (subscription) await subscription.unsubscribe().catch(() => {});
      subscription = null; showState(false); status.textContent = e.message || 'Updates were not activated.';
    }
  });
  save.addEventListener('click', async () => {
    save.disabled = true;
    try { await persist(); window.BriefUX?.track('notification_enabled',{state:topics().sort().join('_')}); status.textContent = 'Saved. Future updates will include only your selected categories.'; }
    catch (e) { status.textContent = e.message; }
    finally { save.disabled = false; }
  });
  disable.addEventListener('click', async () => {
    disable.disabled = true;
    try {
      const endpoint = subscription?.endpoint;
      // Stop local alerts even if the server cannot be reached.
      if (subscription) await subscription.unsubscribe();
      if (endpoint) await rpc('brief_push_unsubscribe', {p_endpoint:endpoint,p_token:token()});
      window.BriefUX?.track('notification_disabled'); subscription = null; localStorage.removeItem(tokenKey); showState(false); status.textContent = 'Updates are off on this device.';
    } catch (_) { disable.disabled = false; status.textContent = 'Browser alerts are stopped. Press Turn off again to remove the saved preference.'; }
  });
})();
