/**
 * Web Push subscription helpers — register service worker, ask for
 * permission, subscribe via Push API, send subscription to backend.
 *
 * iOS note: works only when the site is added to Home Screen as a PWA
 * (iOS 16.4+). Detect via `window.navigator.standalone` for Safari.
 */
import { api } from "./apiClient";

function urlBase64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64);
  const out = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; ++i) out[i] = raw.charCodeAt(i);
  return out;
}

export function pushSupported() {
  return (
    typeof window !== "undefined" &&
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    "Notification" in window
  );
}

export function isIOS() {
  return /iPad|iPhone|iPod/.test(navigator.userAgent || "");
}

export function isStandalone() {
  return (
    window.matchMedia?.("(display-mode: standalone)")?.matches ||
    window.navigator.standalone === true
  );
}

/** True when push *can* work in the current context. iOS Safari needs PWA install. */
export function pushAvailableHere() {
  if (!pushSupported()) return false;
  if (isIOS() && !isStandalone()) return false;
  return true;
}

let _swReady = null;
export async function ensureServiceWorker() {
  if (!_swReady) {
    _swReady = navigator.serviceWorker.register("/sw.js").then(() => navigator.serviceWorker.ready);
  }
  return _swReady;
}

export async function getCurrentSubscription() {
  if (!pushSupported()) return null;
  const reg = await ensureServiceWorker();
  return await reg.pushManager.getSubscription();
}

export async function subscribePush() {
  if (!pushAvailableHere()) {
    throw new Error(
      isIOS() && !isStandalone()
        ? "На iOS добавете сайта на началния екран (Share → Add to Home Screen), за да получавате известия."
        : "Този браузър не поддържа push нотификации."
    );
  }
  const permission = await Notification.requestPermission();
  if (permission !== "granted") {
    throw new Error("Разрешението за известия беше отказано.");
  }

  const reg = await ensureServiceWorker();
  const { data } = await api.get("/push/public-key");
  const publicKey = data?.public_key;
  if (!publicKey) throw new Error("VAPID ключът не е конфигуриран.");

  let sub = await reg.pushManager.getSubscription();
  if (!sub) {
    sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(publicKey),
    });
  }

  await api.post("/push/subscribe", { subscription: sub.toJSON() });
  return sub;
}

export async function unsubscribePush() {
  const sub = await getCurrentSubscription();
  if (!sub) return;
  try {
    await api.post("/push/unsubscribe", { endpoint: sub.endpoint });
  } catch (_) {
    /* best effort */
  }
  await sub.unsubscribe();
}

export async function sendTestPush() {
  await api.post("/push/test");
}
