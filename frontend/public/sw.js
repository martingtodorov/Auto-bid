/* Auto&Bid push service worker — handles incoming Web Push events.
 *
 * - Listens for `push` events delivered by the browser's push service.
 * - Renders a notification using the JSON payload we sent from the
 *   backend ({title, body, url, tag, icon, badge}).
 * - On click, opens or focuses the matching tab.
 *
 * iOS 16.4+ supports this only when the site is installed to the
 * Home Screen as a PWA; on Android Chrome it works in the regular tab.
 */
/* eslint-disable no-restricted-globals */

self.addEventListener("install", (event) => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (_) {
    data = { title: "Auto&Bid", body: event.data ? event.data.text() : "" };
  }

  const title = data.title || "Auto&Bid";
  const options = {
    body: data.body || "",
    icon: data.icon || "/icons/push-icon-192.png",
    badge: data.badge || "/icons/push-badge-72.png",
    tag: data.tag || "auto-bid",
    renotify: true,
    data: { url: data.url || "/", ts: data.ts },
    vibrate: [120, 60, 120],
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const targetUrl = (event.notification.data && event.notification.data.url) || "/";

  event.waitUntil(
    (async () => {
      const clientList = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
      for (const c of clientList) {
        try {
          const u = new URL(c.url);
          if (u.pathname === new URL(targetUrl, u.origin).pathname) {
            return c.focus();
          }
        } catch (_) {
          /* ignore malformed urls */
        }
      }
      if (self.clients.openWindow) {
        return self.clients.openWindow(targetUrl);
      }
    })()
  );
});
