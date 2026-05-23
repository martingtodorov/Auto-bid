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
  seo_title: "Auto&Bid.bg — Автомобилни търгове",
  seo_description: "",
  google_site_verification: "",
  bing_site_verification: "",
  google_analytics_id: "",
  faq_content: "",
  terms_content: "",
  contacts_content: "",
  fees_content: "",
  how_it_works_content: "",
  deindex_mode: false,
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

// Kick one refresh on module import so global meta tags (deindex robots,
// GA, site verification) are applied even on pages that don't call
// `useSiteSettings()` themselves. Browser-only — skipped during SSR.
if (typeof window !== "undefined") {
  refreshSettings();
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

  // Deindex mode — mark <head> with a persistent noindex meta that survives
  // client-side navigation. `setPageMeta()` intentionally does NOT override
  // this element (see the `data-global` attribute check in seo.js).
  const DEINDEX_ID = "deindex-robots";
  const existingDeindex = document.getElementById(DEINDEX_ID);
  if (s.deindex_mode) {
    let el = existingDeindex;
    if (!el) {
      el = document.createElement("meta");
      el.id = DEINDEX_ID;
      el.setAttribute("name", "robots");
      el.setAttribute("data-global", "1");
      head.appendChild(el);
    }
    el.setAttribute("content", "noindex, nofollow, noarchive, nosnippet");
  } else if (existingDeindex) {
    existingDeindex.remove();
  }

  // Dynamic favicon — applies CMS-configured icon URL (link rel="icon").
  const fav = (s.favicon_url || "").trim();
  let favEl = head.querySelector('link[rel="icon"]');
  if (fav) {
    if (!favEl) {
      favEl = document.createElement("link");
      favEl.setAttribute("rel", "icon");
      head.appendChild(favEl);
    }
    if (favEl.getAttribute("href") !== fav) favEl.setAttribute("href", fav);
  }

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
  const fmin = Number(settings?.buyer_fee_min_eur ?? 150);  const fmax = Number(settings?.buyer_fee_max_eur ?? 4000);
  return Math.min(fmax, Math.max(fmin, Math.round((Number(amount) || 0) * pct)));
}

/**
 * Pick the right CMS text for the active language.
 *
 * IMPORTANT: We do NOT fall back across languages. If the admin has set
 * `faq_content_bg` but not `faq_content_ro`, a Romanian visitor MUST see
 * the i18n React default (translated by the app), not the Bulgarian text.
 * Cross-language fallback was a bug — admins explicitly translate per
 * locale so an empty locale field means "use the React-side translation",
 * not "fall back to BG".
 *
 * Returns the value for the EXACT language only. For backwards-compat we
 * still accept the legacy non-suffixed field when the active language IS
 * Bulgarian.
 */
export function pickCmsContent(settings, base, lang) {
  if (!settings) return "";
  const code = (lang || "bg").slice(0, 2);
  const direct = (settings[`${base}_${code}`] || "").trim();
  if (direct) return direct;
  // Legacy compat: accept the non-suffixed field as an alias for BG.
  if (code === "bg") return (settings[base] || "").trim();
  return "";
}

/**
 * Same per-language strictness as pickCmsContent — no cross-language
 * fallback. Returns the HTML override for the EXACT language only.
 */
export function pickCmsHtml(settings, base, lang) {
  if (!settings) return "";
  const code = (lang || "bg").slice(0, 2);
  return (settings[`${base}_html_${code}`] || "").trim();
}
