import { useEffect, useState } from "react";
import { api } from "./apiClient";

// Module-level cache so all components share one fetch.
let _cached = null;
let _inflight = null;
const _subscribers = new Set();

const DEFAULTS = {
  buyer_fee_pct: 2.0,
  buyer_fee_min_eur: 150,
  buyer_fee_max_eur: 4000,
  seo_title: "autobids.bg — Автомобилни търгове",
  seo_description: "",
  google_site_verification: "",
  bing_site_verification: "",
  google_analytics_id: "",
  faq_content: "",
  terms_content: "",
  contacts_content: "",
  fees_content: "",
  how_it_works_content: "",
};

export async function refreshSettings() {
  try {
    const { data } = await api.get("/settings");
    _cached = { ...DEFAULTS, ...data };
    applyVerificationTags(_cached);
    _subscribers.forEach((cb) => cb(_cached));
    return _cached;
  } catch (e) {
    _cached = _cached || DEFAULTS;
    return _cached;
  }
}

// Inject Google / Bing site verification meta tags + GA script once settings load.
function applyVerificationTags(s) {
  if (typeof document === "undefined") return;
  const head = document.head;
  const ensure = (name, content) => {
    const sel = `meta[name="${name}"]`;
    let el = head.querySelector(sel);
    if (!content) {
      if (el) el.remove();
      return;
    }
    if (!el) {
      el = document.createElement("meta");
      el.setAttribute("name", name);
      head.appendChild(el);
    }
    el.setAttribute("content", content);
  };
  ensure("google-site-verification", s.google_site_verification);
  ensure("msvalidate.01", s.bing_site_verification);

  // Google Analytics gtag.js (only if configured)
  const gaId = s.google_analytics_id;
  const gaScriptId = "ga-gtag-src";
  const gaInitId = "ga-gtag-init";
  const existingSrc = document.getElementById(gaScriptId);
  const existingInit = document.getElementById(gaInitId);
  if (gaId && /^G-[A-Z0-9]{4,}$/.test(gaId)) {
    if (!existingSrc) {
      const s1 = document.createElement("script");
      s1.id = gaScriptId;
      s1.async = true;
      s1.src = `https://www.googletagmanager.com/gtag/js?id=${gaId}`;
      head.appendChild(s1);
    }
    if (!existingInit) {
      const s2 = document.createElement("script");
      s2.id = gaInitId;
      s2.text = `window.dataLayer = window.dataLayer || [];function gtag(){dataLayer.push(arguments);}gtag('js', new Date());gtag('config', '${gaId}', { anonymize_ip: true });`;
      head.appendChild(s2);
    }
  } else {
    if (existingSrc) existingSrc.remove();
    if (existingInit) existingInit.remove();
  }
}

export function useSiteSettings() {
  const [settings, setSettings] = useState(_cached || DEFAULTS);
  useEffect(() => {
    const cb = (s) => setSettings(s);
    _subscribers.add(cb);
    if (_cached) {
      setSettings(_cached);
    } else if (!_inflight) {
      _inflight = refreshSettings().finally(() => { _inflight = null; });
    }
    return () => { _subscribers.delete(cb); };
  }, []);
  return settings;
}

// Compute buyer fee locally using settings (mirror of backend _buyer_fee).
export function computeBuyerFee(amount, settings) {
  const pct = Number(settings?.buyer_fee_pct ?? 2) / 100;
  const fmin = Number(settings?.buyer_fee_min_eur ?? 150);
  const fmax = Number(settings?.buyer_fee_max_eur ?? 4000);
  return Math.min(fmax, Math.max(fmin, Math.round((Number(amount) || 0) * pct)));
}

/**
 * Pick the right CMS text for the active language with graceful fallback chain:
 *   <base>_<lang> → <base>_bg → <base> (legacy BG field) → ""
 * `base` is one of: "faq_content", "terms_content", "fees_content",
 * "contacts_content", "how_it_works_content".
 */
export function pickCmsContent(settings, base, lang) {
  if (!settings) return "";
  const code = (lang || "bg").slice(0, 2);
  return (
    (settings[`${base}_${code}`] || "").trim() ||
    (settings[`${base}_bg`] || "").trim() ||
    (settings[base] || "").trim() ||
    ""
  );
}
