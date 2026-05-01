import React, { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ShieldCheck, X } from "lucide-react";
import { useAuth } from "../lib/auth";

const DISMISS_KEY = "abm:2fa-prompt-dismissed";

/**
 * One-time banner shown to email-verified users who haven't enabled 2FA yet.
 * Persists dismissal in localStorage so users can ignore it without nagging,
 * but it reappears the next time they clear browser data — mild pressure to
 * adopt 2FA without being annoying.
 */
export default function TwoFactorPromptBanner() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [dismissed, setDismissed] = useState(() => {
    try { return localStorage.getItem(DISMISS_KEY) === "1"; } catch (_e) { return false; }
  });

  if (!user) return null;
  if (!user.email_verified) return null;       // banner appears AFTER email verification
  if (user.totp_enabled) return null;          // already on
  if (dismissed) return null;

  const close = () => {
    try { localStorage.setItem(DISMISS_KEY, "1"); } catch (_e) { /* noop */ }
    setDismissed(true);
  };

  return (
    <div
      className="bg-emerald-50 border-b border-emerald-200 text-emerald-900"
      data-testid="twofa-prompt-banner"
    >
      <div className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-10 py-2.5 flex items-center justify-between gap-4 text-sm flex-wrap">
        <div className="flex items-center gap-2 min-w-0">
          <ShieldCheck size={16} className="shrink-0" />
          <span className="truncate">
            {t(
              "twofa_prompt.body",
              "Защитете акаунта си с допълнителна стъпка при вход (двуфакторна автентикация)."
            )}
          </span>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          <Link
            to="/settings"
            className="px-3 py-1 rounded-card bg-emerald-700 text-white text-xs font-semibold hover:bg-emerald-800"
            data-testid="twofa-prompt-cta"
          >
            {t("twofa_prompt.cta", "Включи 2FA")}
          </Link>
          <button
            onClick={close}
            aria-label="Затвори"
            data-testid="twofa-prompt-dismiss"
            className="p-1 hover:bg-emerald-100 rounded"
          >
            <X size={14} />
          </button>
        </div>
      </div>
    </div>
  );
}
