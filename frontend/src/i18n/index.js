import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import LanguageDetector from "i18next-browser-languagedetector";

import bg from "./locales/bg.json";
import ro from "./locales/ro.json";
import en from "./locales/en.json";

i18n
  .use(LanguageDetector)
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
      order: ["localStorage", "navigator"],
      lookupLocalStorage: "autobids_lang",
      caches: ["localStorage"],
    },
  });

export default i18n;
