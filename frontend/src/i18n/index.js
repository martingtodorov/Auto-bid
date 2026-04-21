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
const DOMAIN_BG = (process.env.REACT_APP_DOMAIN_BG || "autobids.bg").toLowerCase();
const DOMAIN_RO = (process.env.REACT_APP_DOMAIN_RO || "autobids.ro").toLowerCase();
const DOMAIN_EN = (process.env.REACT_APP_DOMAIN_EN || "autobids.com").toLowerCase();

/** Returns a language code based on the current hostname, or null if no match. */
export function detectLanguageFromHost() {
  if (typeof window === "undefined") return null;
  const host = (window.location.hostname || "").toLowerCase();
  if (!host) return null;
  if (host.endsWith(DOMAIN_RO)) return "ro";
  if (host.endsWith(DOMAIN_EN)) return "en";
  if (host.endsWith(DOMAIN_BG)) return "bg";
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
