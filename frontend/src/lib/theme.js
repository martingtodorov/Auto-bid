/**
 * Theme manager — light / dark / system.
 *
 * Sets `data-theme` on <html>; CSS reads it via the `html[data-theme="dark"]`
 * selector in index.css. Persists choice in localStorage; if the user picks
 * "system" we follow `prefers-color-scheme` and react to OS-level changes.
 */
const KEY = "ab.theme";
const THEMES = ["light", "dark"];

export function getStoredTheme() {
  if (typeof localStorage === "undefined") return "light";
  const v = localStorage.getItem(KEY);
  return THEMES.includes(v) ? v : "light";
}

export function applyTheme(theme) {
  const eff = THEMES.includes(theme) ? theme : "light";
  document.documentElement.setAttribute("data-theme", eff);
  // Mobile browser address-bar tint
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
  localStorage.setItem(KEY, theme);
  applyTheme(theme);
  window.dispatchEvent(new CustomEvent("ab:theme-changed", { detail: { theme } }));
}

/** Boot — call from index.js so the first paint is correct (no flash). */
export function bootTheme() {
  applyTheme(getStoredTheme());
}
