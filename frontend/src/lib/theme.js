/**
 * Theme manager — light / dark / system.
 *
 * Sets `data-theme` on <html>; CSS reads it via the `html[data-theme="dark"]`
 * selector in index.css. Persists choice in localStorage; if the user picks
 * "system" we follow `prefers-color-scheme` and react to OS-level changes.
 */
const KEY = "ab.theme";
const THEMES = ["light", "dark", "system"];

function systemPrefersDark() {
  return typeof window !== "undefined" && window.matchMedia
    ? window.matchMedia("(prefers-color-scheme: dark)").matches
    : false;
}

function effective(theme) {
  return theme === "system" ? (systemPrefersDark() ? "dark" : "light") : theme;
}

export function getStoredTheme() {
  if (typeof localStorage === "undefined") return "system";
  const v = localStorage.getItem(KEY);
  return THEMES.includes(v) ? v : "system";
}

export function applyTheme(theme) {
  const eff = effective(theme);
  document.documentElement.setAttribute("data-theme", eff);
  // Mobile browser address-bar tint
  let meta = document.head.querySelector('meta[name="theme-color"]');
  if (!meta) {
    meta = document.createElement("meta");
    meta.setAttribute("name", "theme-color");
    document.head.appendChild(meta);
  }
  meta.setAttribute("content", eff === "dark" ? "#101418" : "#ffffff");
}

export function setTheme(theme) {
  if (!THEMES.includes(theme)) theme = "system";
  localStorage.setItem(KEY, theme);
  applyTheme(theme);
  window.dispatchEvent(new CustomEvent("ab:theme-changed", { detail: { theme } }));
}

/** Boot — call from index.js so the first paint is correct (no flash). */
export function bootTheme() {
  applyTheme(getStoredTheme());
  if (window.matchMedia) {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = () => {
      if (getStoredTheme() === "system") applyTheme("system");
    };
    mq.addEventListener?.("change", handler);
  }
}
