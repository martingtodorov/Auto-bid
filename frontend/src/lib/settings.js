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
  seo_title: "AutoBid.bg — Автомобилни търгове",
  seo_description: "",
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
    _subscribers.forEach((cb) => cb(_cached));
    return _cached;
  } catch (e) {
    _cached = _cached || DEFAULTS;
    return _cached;
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
