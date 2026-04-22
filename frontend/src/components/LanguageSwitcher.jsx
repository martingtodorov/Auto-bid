import React from "react";
import { useTranslation } from "react-i18next";
import { Globe } from "lucide-react";
import { externalUrlForLang, LANG_DOMAINS } from "../i18n";

export default function LanguageSwitcher({ className = "" }) {
  const { i18n } = useTranslation();
  const langs = [
    { code: "bg", label: "BG" },
    { code: "ro", label: "RO" },
    { code: "en", label: "EN" },
  ];
  const change = (lng) => {
    i18n.changeLanguage(lng);
    try { localStorage.setItem("autobids_lang", lng); } catch (_e) { /* ignore */ }
  };
  const current = i18n.resolvedLanguage || "bg";

  return (
    <div className={`inline-flex items-center gap-1 rounded-card border border-[hsl(var(--line))] bg-white text-xs overflow-hidden ${className}`} data-testid="language-switcher">
      <span className="pl-2 text-[hsl(var(--ink-muted))]"><Globe size={12} /></span>
      {langs.map((l) => {
        const isActive = current === l.code;
        const extUrl = externalUrlForLang(l.code);
        const cls = `px-2 py-1.5 transition-colors ${isActive ? "bg-[hsl(var(--ink))] text-white" : "hover:bg-[hsl(var(--surface))]"}`;
        if (extUrl) {
          return (
            <a
              key={l.code}
              href={extUrl}
              hrefLang={l.code}
              className={cls}
              data-testid={`lang-${l.code}`}
              aria-label={`Switch to ${LANG_DOMAINS[l.code]}`}
              title={LANG_DOMAINS[l.code]}
              rel="alternate"
            >
              {l.label}
            </a>
          );
        }
        return (
          <button
            key={l.code}
            onClick={() => change(l.code)}
            className={cls}
            data-testid={`lang-${l.code}`}
            aria-label={`Switch to ${l.label}`}
          >
            {l.label}
          </button>
        );
      })}
    </div>
  );
}
