import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import { Mail } from "lucide-react";
import { api } from "../lib/apiClient";
import { useAuth } from "../lib/auth";

/**
 * Top-of-page banner shown to logged-in users whose email is still not
 * verified AND whose account is in the post-rollout cohort
 * (`verification_required=true`). Lets them resend the verification email.
 */
export default function VerifyEmailBanner() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  if (!user) return null;
  if (!user.verification_required) return null;
  if (user.email_verified) return null;

  const resend = async () => {
    setBusy(true);
    setErr("");
    setMsg("");
    try {
      await api.post("/auth/resend-verification");
      setMsg(t("verify_banner.sent", "Изпратихме нов линк на имейла ви."));
    } catch (e) {
      const detail = e?.response?.data?.detail;
      setErr(typeof detail === "string" ? detail : t("verify_banner.err", "Грешка при изпращане. Опитайте по-късно."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="bg-amber-50 border-b border-amber-200 text-amber-900"
      data-testid="verify-email-banner"
    >
      <div className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-10 py-2.5 flex items-center justify-between gap-4 text-sm flex-wrap">
        <div className="flex items-center gap-2 min-w-0">
          <Mail size={16} className="shrink-0" />
          <span className="truncate">
            {t(
              "verify_banner.body",
              "Потвърдете имейла си, за да наддавате, коментирате и продавате."
            )}
          </span>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          {msg && <span className="text-emerald-700">{msg}</span>}
          {err && <span className="text-[hsl(var(--danger))]" data-testid="verify-banner-error">{err}</span>}
          <button
            onClick={resend}
            disabled={busy}
            className="px-3 py-1 rounded-card bg-amber-900 text-white text-xs font-semibold disabled:opacity-50"
            data-testid="verify-banner-resend"
          >
            {busy
              ? t("verify_banner.sending", "Изпращане…")
              : t("verify_banner.resend", "Изпрати отново")}
          </button>
        </div>
      </div>
    </div>
  );
}
