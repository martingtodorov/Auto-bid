import React, { useEffect, useState } from "react";
import { Cookie, X } from "lucide-react";
import { useTranslation } from "react-i18next";

const KEY = "autobids_cookie_consent_v1";

/**
 * GDPR cookie consent banner.
 * Stores "accepted" | "rejected" in localStorage. Persisted across sessions.
 */
export default function CookieConsentBanner() {
  const { t } = useTranslation();
  const [status, setStatus] = useState(null);

  useEffect(() => {
    try { setStatus(localStorage.getItem(KEY) || null); } catch (_e) { /* ignore */ }
  }, []);

  const set = (value) => {
    try { localStorage.setItem(KEY, value); } catch (_e) { /* ignore */ }
    setStatus(value);
  };

  if (status) return null;

  return (
    <div
      className="fixed bottom-0 left-0 right-0 z-[60] bg-[hsl(var(--ink))] text-white px-4 py-4 sm:px-6 shadow-2xl border-t border-[hsl(var(--accent))]"
      data-testid="cookie-banner"
      role="dialog"
      aria-label="Cookie consent"
    >
      <div className="max-w-[1200px] mx-auto flex items-start gap-4 flex-wrap">
        <Cookie size={22} className="text-[hsl(var(--accent))] mt-1 shrink-0" />
        <div className="flex-1 min-w-[240px] text-sm leading-relaxed">
          <strong className="block mb-1">{t("cookies.title")}</strong>
          <p className="text-white/80 text-xs">
            {t("cookies.body")}{" "}
            <a href="/privacy" className="underline text-[hsl(var(--accent))]">{t("cookies.privacy_link")}</a>.
          </p>
        </div>
        <div className="flex items-center gap-2 ml-auto">
          <button onClick={() => set("rejected")} className="px-4 py-2 text-xs rounded-card border border-white/30 hover:bg-white/10" data-testid="cookie-reject">{t("cookies.reject")}</button>
          <button onClick={() => set("accepted")} className="px-5 py-2 text-xs rounded-card bg-[hsl(var(--accent))] text-white font-medium" data-testid="cookie-accept">{t("cookies.accept")}</button>
          <button onClick={() => set("rejected")} aria-label="Close" className="p-1 hover:bg-white/10 rounded-full"><X size={16} /></button>
        </div>
      </div>
    </div>
  );
}
