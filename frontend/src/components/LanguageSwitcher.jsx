import React from "react";
import { useTranslation } from "react-i18next";
import { externalUrlForLang, LANG_DOMAINS } from "../i18n";
import { api } from "../lib/apiClient";

const LANGS = [
  { code: "bg", label: "BG" },
  { code: "ro", label: "RO" },
  { code: "en", label: "EN" },
];

export default function LanguageSwitcher({ className = "" }) {
  const { i18n } = useTranslation();

  const change = (lng) => {
    i18n.changeLanguage(lng);
    try { localStorage.setItem("autobids_lang", lng); } catch (_e) { /* ignore */ }
    try {
      if (typeof localStorage !== "undefined" && localStorage.getItem("autobid_token")) {
        api.post("/auth/me/lang", { lang: lng }).catch(() => {});
      }
    } catch (_e) { /* ignore */ }
  };

  const current = i18n.resolvedLanguage || "bg";
  const currentLabel = (LANGS.find((l) => l.code === current) || LANGS[0]).label;
  const others = LANGS.filter((l) => l.code !== current);

  // The desktop pattern: a small circular pill showing the current language;
  // hovering it reveals the other two below. Keyboard-accessible via
  // `:focus-within` on the wrapper.
  return (
    <div
      className={`relative group ${className}`}
      data-testid="language-switcher"
    >
      <button
        type="button"
        className="w-9 h-9 rounded-full border border-[hsl(var(--line))] bg-[hsl(var(--bg))] text-[11px] font-semibold tracking-wide flex items-center justify-center hover:border-[hsl(var(--accent))] transition-colors"
        aria-label={`Current language: ${currentLabel}`}
        data-testid={`lang-current-${current}`}
      >
        {currentLabel}
      </button>
      <div className="absolute right-0 top-full pt-2 hidden group-hover:block group-focus-within:block z-40">
        <div className="rounded-card border border-[hsl(var(--line))] bg-[hsl(var(--surface))] shadow-xl py-1.5 min-w-[100px]">
          {others.map((l) => {
            const extUrl = externalUrlForLang(l.code);
            const cls = "block w-full text-left px-3 py-1.5 text-xs font-semibold tracking-wide text-[hsl(var(--ink))] hover:bg-[hsl(var(--bg))] transition-colors";
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
                type="button"
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
      </div>
    </div>
  );
}
