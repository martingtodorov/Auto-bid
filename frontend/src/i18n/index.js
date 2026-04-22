import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import LanguageDetector from "i18next-browser-languagedetector";

import bg from "./locales/bg.json";
import ro from "./locales/ro.json";
import en from "./locales/en.json";

/**
 * Domain → language mapping.
 * Configurable via env variables (set at build time):
 *   REACT_APP_DOMAIN_BG=autobids.bg
 *   REACT_APP_DOMAIN_RO=autobids.ro
 *   REACT_APP_DOMAIN_EN=autobids.com
 * Defaults assume the three TLD variants that follow the brand convention.
 * A match is "endsWith" so staging/preview subdomains (e.g. `preview.autobids.ro`) work too.
 */
const DOMAIN_BG = (process.env.REACT_APP_DOMAIN_BG || "auto-bid.bg").toLowerCase();
const DOMAIN_RO = (process.env.REACT_APP_DOMAIN_RO || "auto-bid.ro").toLowerCase();
const DOMAIN_EN = (process.env.REACT_APP_DOMAIN_EN || "auto-bid.com").toLowerCase();

export const LANG_DOMAINS = { bg: DOMAIN_BG, ro: DOMAIN_RO, en: DOMAIN_EN };

/** Brand suffix shown in the logo for a given language code. */
export function brandTldForLang(code) {
  const c = (code || "bg").slice(0, 2);
  if (c === "ro") return ".ro";
  if (c === "en") return ".com";
  return ".bg";
}

/**
 * Returns an absolute URL on the target language's domain, preserving the
 * current path + query + hash. Returns null when the three language domains
 * cannot be distinguished (preview/staging single-host deployments) or when
 * the target would equal the current host — in those cases the caller should
 * fall back to in-page i18n switching.
 */
export function externalUrlForLang(code) {
  if (typeof window === "undefined") return null;
  const target = LANG_DOMAINS[code];
  if (!target) return null;
  // Flag "staging": when all three domain env values resolve to the same host,
  // or when the current host doesn't end with any of them.
  const uniqueDomains = new Set(Object.values(LANG_DOMAINS));
  if (uniqueDomains.size < 3) return null;
  const host = (window.location.hostname || "").toLowerCase();
  const onKnown = Object.values(LANG_DOMAINS).some((d) => host.endsWith(d));
  if (!onKnown) return null;
  if (host.endsWith(target)) return null; // already there
  return `https://${target}${window.location.pathname}${window.location.search}${window.location.hash}`;
}

/** Returns a language code based on the current hostname, or null if no match. */
export function detectLanguageFromHost() {
  if (typeof window === "undefined") return null;
  const host = (window.location.hostname || "").toLowerCase();
  if (!host) return null;
  if (host.endsWith(LANG_DOMAINS.ro)) return "ro";
  if (host.endsWith(LANG_DOMAINS.en)) return "en";
  if (host.endsWith(LANG_DOMAINS.bg)) return "bg";
  return null;
}

// Custom detector that always runs FIRST and only returns when a domain match is found.
// Users can still manually switch via LanguageSwitcher (writes to localStorage).
const DomainDetector = {
  name: "domain",
  lookup: () => detectLanguageFromHost(),
  cacheUserLanguage: () => {
    /* no-op — we never persist the domain choice, each visit re-detects */
  },
};

const detector = new LanguageDetector();
detector.addDetector(DomainDetector);

i18n
  .use(detector)
  .use(initReactI18next)
  .init({
    resources: {
      bg: { translation: bg },
      ro: { translation: ro },
      en: { translation: en },
    },
    fallbackLng: "bg",
    supportedLngs: ["bg", "ro", "en"],
    interpolation: { escapeValue: false },
    detection: {
      // Order: explicit user choice (localStorage) > domain > browser > default
      order: ["localStorage", "domain", "navigator"],
      lookupLocalStorage: "autobids_lang",
      caches: ["localStorage"],
    },
  });

export default i18n;
