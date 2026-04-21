import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API_BASE = `${BACKEND_URL}/api`;

export const api = axios.create({
  baseURL: API_BASE,
});

api.interceptors.request.use((config) => {
  const t = localStorage.getItem("autobid_token");
  if (t) config.headers.Authorization = `Bearer ${t}`;
  return config;
});

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

export function formatKM(value) {
  if (value == null) return "—";
  return new Intl.NumberFormat("bg-BG").format(value) + " км";
}

export function timeLeft(isoString) {
  const end = new Date(isoString).getTime();
  const now = Date.now();
  const diff = end - now;
  if (diff <= 0) return { label: "Приключил", expired: true };
  const days = Math.floor(diff / (1000 * 60 * 60 * 24));
  const hours = Math.floor((diff / (1000 * 60 * 60)) % 24);
  const minutes = Math.floor((diff / (1000 * 60)) % 60);
  const seconds = Math.floor((diff / 1000) % 60);
  if (days >= 1) return { label: `${days}д ${hours}ч`, expired: false, days, hours, minutes, seconds };
  if (hours >= 1) return { label: `${hours}ч ${minutes}м`, expired: false, days, hours, minutes, seconds, urgent: hours < 6 };
  return { label: `${minutes}м ${seconds}с`, expired: false, urgent: true, days, hours, minutes, seconds };
}
