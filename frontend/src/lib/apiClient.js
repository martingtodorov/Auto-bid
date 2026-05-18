import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";
// Empty BACKEND_URL → use relative `/api/*`. Critical for production where
// each brand domain (autoandbid.com / .bg / .ro) terminates its own TLS at
// nginx and proxies /api to the same backend. Same-origin requests = cookies
// (httpOnly auth + CSRF) work without cross-domain SameSite gymnastics.
export const API_BASE = `${BACKEND_URL}/api`;

// --- C3 cookie auth helpers ---
function readCookie(name) {
  if (typeof document === "undefined") return null;
  const m = document.cookie.match(new RegExp("(?:^|; )" + name.replace(/([.$?*|{}()[\]\\/+^])/g, "\\$1") + "=([^;]*)"));
  return m ? decodeURIComponent(m[1]) : null;
}

export const api = axios.create({
  baseURL: API_BASE,
  withCredentials: true, // C3: изпращай httpOnly auth cookie
});

api.interceptors.request.use((config) => {
  // Backwards-compatible Bearer fallback (за стари сесии в localStorage,
  // докато cookie-то се установи при следващ login).
  const t = typeof localStorage !== "undefined" ? localStorage.getItem("autobid_token") : null;
  if (t && !config.headers.Authorization) {
    config.headers.Authorization = `Bearer ${t}`;
  }
  // CSRF double-submit за мутиращи заявки.
  const method = (config.method || "get").toLowerCase();
  if (["post", "put", "patch", "delete"].includes(method)) {
    const csrf = readCookie("csrf_token");
    if (csrf) config.headers["X-CSRF-Token"] = csrf;
  }
  return config;
});

/** Map an i18n short code to an Intl BCP47 locale for date / number formatting. */
export function intlLocale(lng) {
  const code = (lng || "bg").slice(0, 2);
  if (code === "ro") return "ro-RO";
  if (code === "en") return "en-GB";
  return "bg-BG";
}

export function formatEUR(value) {
  if (value == null) return "—";
  return new Intl.NumberFormat("bg-BG", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(value);
}

/** BGN (лв.) — fixed peg 1 EUR = 1.95583 BGN */
export function formatBGN(value) {
  if (value == null) return "—";
  const bgn = Number(value) * 1.95583;
  return new Intl.NumberFormat("bg-BG", { maximumFractionDigits: 0 }).format(bgn) + " лв.";
}

/** RON (lei) — approximate EUR→RON rate; adjust `RON_RATE` if BNR snapshot is preferred. */
const RON_RATE = 4.97;
export function formatRON(value) {
  if (value == null) return "—";
  const ron = Number(value) * RON_RATE;
  return new Intl.NumberFormat("ro-RO", { maximumFractionDigits: 0 }).format(ron) + " lei";
}

/**
 * Secondary local-currency formatter that picks BGN / RON / (none for EN)
 * based on the current i18n language.  Returns an empty string for English
 * (EUR already shown by formatEUR — no secondary needed).
 */
export function formatLocal(value, lng) {
  const code = (lng || "bg").slice(0, 2);
  if (code === "ro") return formatRON(value);
  if (code === "en") return ""; // EN users don't need a secondary currency
  return formatBGN(value);
}

/**
 * Format an odometer reading as a localized number with a unit suffix.
 *
 * The `lang` parameter is optional — when omitted (e.g. legacy callers
 * that haven't been migrated), we fall back to Bulgarian formatting +
 * Cyrillic "км". Pass the active i18n language to get the right unit:
 *   - bg → "км"
 *   - en → "km"
 *   - ro → "km"
 *
 * The thousands separator follows the user's locale (BG uses a non-breaking
 * space, EN uses a comma, RO uses a dot) which is what `Intl.NumberFormat`
 * produces natively. Returns an em-dash for null/undefined values.
 */
export function formatKM(value, lang) {
  if (value == null) return "—";
  const code = (lang || "bg").toLowerCase().slice(0, 2);
  // Intl locale tags — note `ro-RO` uses dots as thousands separators.
  const locale = code === "en" ? "en-GB" : code === "ro" ? "ro-RO" : "bg-BG";
  const unit = code === "bg" ? "км" : "km";
  return new Intl.NumberFormat(locale).format(value) + " " + unit;
}

/**
 * Compute time remaining to `isoString`.
 * Returns numeric parts + flags (expired/urgent). The label is produced by
 * `formatTimeLeft()` because it depends on the active i18n language.
 *
 * The returned `.label` is a BG fallback kept for legacy callers; prefer
 * `formatTimeLeft(tl, t)` in new code.
 */
export function timeLeft(isoString) {
  const end = new Date(isoString).getTime();
  const now = Date.now();
  const diff = end - now;
  if (diff <= 0) return { label: "Приключил", expired: true, days: 0, hours: 0, minutes: 0, seconds: 0 };
  const days = Math.floor(diff / (1000 * 60 * 60 * 24));
  const hours = Math.floor((diff / (1000 * 60 * 60)) % 24);
  const minutes = Math.floor((diff / (1000 * 60)) % 60);
  const seconds = Math.floor((diff / 1000) % 60);
  let label;
  if (days >= 1) label = `${days}д ${hours}ч`;
  else if (hours >= 1) label = `${hours}ч ${minutes}м`;
  else label = `${minutes}м ${seconds}с`;
  return { label, expired: false, urgent: days < 1 && (hours < 6), days, hours, minutes, seconds };
}

/**
 * Render a `timeLeft` result using the current i18n translator `t`.
 * Keys used: `time.ended`, `time.days_hours`, `time.hours_minutes`, `time.minutes_seconds`.
 */
export function formatTimeLeft(tl, t) {
  if (!tl) return "";
  if (tl.expired) return t("time.ended");
  if (tl.days >= 1) return t("time.days_hours", { d: tl.days, h: tl.hours });
  if (tl.hours >= 1) return t("time.hours_minutes", { h: tl.hours, m: tl.minutes });
  return t("time.minutes_seconds", { m: tl.minutes, s: tl.seconds });
}
