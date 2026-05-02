/**
 * Landing-page cache — lives in sessionStorage so instant back-nav to
 * the homepage shows content immediately, and gets refreshed once a
 * minute from the background so auctions that have ended / been pulled
 * disappear without a hard reload.
 *
 * Only used by `LandingPage.jsx` — small surface by design.
 */
import { api } from "./apiClient";

const KEY = "autobid:landing_v1";
const TTL_MS = 60 * 1000; // 60s — matches the user-visible refresh cadence

export function readLandingCache() {
  if (typeof sessionStorage === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed.ts !== "number") return null;
    return parsed; // { ts, live, featured, sold }
  } catch {
    return null;
  }
}

function writeLandingCache(payload) {
  if (typeof sessionStorage === "undefined") return;
  try {
    sessionStorage.setItem(KEY, JSON.stringify({ ts: Date.now(), ...payload }));
  } catch {
    /* quota / disabled — ignore, in-memory state still works */
  }
}

export function landingCacheIsFresh(entry) {
  return !!entry && Date.now() - entry.ts < TTL_MS;
}

/**
 * Fetches all three landing-page lists in parallel, updates sessionStorage,
 * and returns `{ live, featured, sold }`. Throws on network failure —
 * caller decides whether to keep rendering the stale cache.
 */
export async function fetchLandingData() {
  const [l, f, s, h] = await Promise.all([
    api.get("/auctions", { params: { sort: "ending_soon", status: "live", limit: 6, view: "list" } }),
    api.get("/auctions/featured", { params: { view: "list" } }),
    api.get("/auctions/sold", { params: { view: "list" } }),
    api.get("/auctions/hero"),
  ]);
  const payload = {
    live: l.data || [],
    featured: f.data || [],
    sold: s.data || [],
    hero: h.data || [],
  };
  writeLandingCache(payload);
  return payload;
}
