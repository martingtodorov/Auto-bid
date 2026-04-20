import React from "react";
import { useTranslation } from "react-i18next";
import { Globe } from "lucide-react";

export default function LanguageSwitcher({ className = "" }) {
  const { i18n } = useTranslation();
  const langs = [{ code: "bg", flag: "🇧🇬", label: "BG" }, { code: "ro", flag: "🇷🇴", label: "RO" }];
  const change = (lng) => {
    i18n.changeLanguage(lng);
    try { localStorage.setItem("autobids_lang", lng); } catch (_e) { /* ignore */ }
  };
  const current = i18n.resolvedLanguage || "bg";
  return (
    <div className={`inline-flex items-center gap-1 rounded-card border border-[hsl(var(--line))] bg-white text-xs overflow-hidden ${className}`} data-testid="language-switcher">
      <span className="pl-2 text-[hsl(var(--ink-muted))]"><Globe size={12} /></span>
      {langs.map((l) => (
        <button
          key={l.code}
          onClick={() => change(l.code)}
          className={`px-2 py-1.5 transition-colors ${current === l.code ? "bg-[hsl(var(--ink))] text-white" : "hover:bg-[hsl(var(--surface))]"}`}
          data-testid={`lang-${l.code}`}
          aria-label={`Switch to ${l.label}`}
        >
          {l.label}
        </button>
      ))}
    </div>
  );
}
