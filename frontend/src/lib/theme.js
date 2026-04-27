/**
 * Theme manager — light / dark.
 *
 * Sets `data-theme` on <html>; CSS reads it via `html[data-theme="dark"]`
 * in index.css. The user's choice is persisted in BOTH a first-party cookie
 * (1 year, SameSite=Lax) AND localStorage so a re-login or a cross-tab flow
 * carries the preference. Cookie is the source of truth — localStorage is
 * a fallback for embedded WebViews where document.cookie is restricted.
 */
const KEY = "ab.theme";
const COOKIE = "ab_theme";
const THEMES = ["light", "dark"];
const ONE_YEAR = 60 * 60 * 24 * 365;

function readCookie(name) {
  if (typeof document === "undefined") return null;
  const match = document.cookie
    .split("; ")
    .find((row) => row.startsWith(name + "="));
  return match ? decodeURIComponent(match.split("=")[1]) : null;
}

function writeCookie(name, value) {
  if (typeof document === "undefined") return;
  const secure = window.location.protocol === "https:" ? "; Secure" : "";
  document.cookie = `${name}=${encodeURIComponent(value)}; path=/; max-age=${ONE_YEAR}; SameSite=Lax${secure}`;
}

export function getStoredTheme() {
  const cookie = readCookie(COOKIE);
  if (THEMES.includes(cookie)) return cookie;
  if (typeof localStorage !== "undefined") {
    const v = localStorage.getItem(KEY);
    if (THEMES.includes(v)) return v;
  }
  return "light";
}

export function applyTheme(theme) {
  const eff = THEMES.includes(theme) ? theme : "light";
  document.documentElement.setAttribute("data-theme", eff);
  let meta = document.head.querySelector('meta[name="theme-color"]');
  if (!meta) {
    meta = document.createElement("meta");
    meta.setAttribute("name", "theme-color");
    document.head.appendChild(meta);
  }
  meta.setAttribute("content", eff === "dark" ? "#000000" : "#ffffff");
}

export function setTheme(theme) {
  if (!THEMES.includes(theme)) theme = "light";
  writeCookie(COOKIE, theme);
  if (typeof localStorage !== "undefined") {
    try { localStorage.setItem(KEY, theme); } catch (e) {}
  }
  applyTheme(theme);
  window.dispatchEvent(new CustomEvent("ab:theme-changed", { detail: { theme } }));
}

/** Boot — call from index.js so the first paint is correct (no flash). */
export function bootTheme() {
  applyTheme(getStoredTheme());
}
