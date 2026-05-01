import React, { useEffect, useState } from "react";
import { useSearchParams, Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { CheckCircle2, XCircle, Loader2 } from "lucide-react";
import { api } from "../lib/apiClient";
import { useAuth } from "../lib/auth";

/**
 * Email verification landing page.
 * Reads ?token=... from the URL, POSTs it to /api/auth/verify-email and
 * shows success / error state. On success, refreshes auth state so any
 * gated UI immediately becomes available.
 */
export default function VerifyEmailPage() {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { refresh } = useAuth();
  const token = params.get("token");
  const [status, setStatus] = useState("loading"); // loading | ok | error
  const [message, setMessage] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!token) {
        setStatus("error");
        setMessage(t("verify_email.no_token", "Липсва токен в линка."));
        return;
      }
      try {
        await api.post("/auth/verify-email", { token });
        if (cancelled) return;
        try { await refresh(); } catch (_e) { /* noop */ }
        setStatus("ok");
        setMessage(t("verify_email.success", "Имейлът е потвърден успешно. Вече можете да наддавате, коментирате и продавате."));
      } catch (e) {
        if (cancelled) return;
        setStatus("error");
        const detail = e?.response?.data?.detail || t("verify_email.invalid", "Невалиден или изтекъл линк.");
        setMessage(typeof detail === "string" ? detail : t("verify_email.invalid", "Невалиден или изтекъл линк."));
      }
    })();
    return () => { cancelled = true; };
  }, [token, t, refresh]);

  return (
    <main className="min-h-[70vh] flex items-center justify-center px-4" data-testid="verify-email-page">
      <div className="max-w-md w-full text-center rounded-card border border-[hsl(var(--line))] bg-white p-8 lg:p-10">
        {status === "loading" && (
          <>
            <Loader2 className="mx-auto animate-spin text-[hsl(var(--accent))]" size={48} />
            <h1 className="font-serif text-2xl mt-5">{t("verify_email.checking", "Потвърждаване…")}</h1>
          </>
        )}

        {status === "ok" && (
          <>
            <CheckCircle2 className="mx-auto text-[hsl(var(--accent))]" size={56} />
            <h1 className="font-serif text-2xl mt-5">{t("verify_email.title_ok", "Имейлът е потвърден")}</h1>
            <p className="mt-3 text-sm text-[hsl(var(--ink-muted))]">{message}</p>
            <button
              onClick={() => navigate("/dashboard")}
              className="btn btn-primary mt-6"
              data-testid="verify-email-go-dashboard"
            >
              {t("verify_email.go_dashboard", "Към профила")}
            </button>
          </>
        )}

        {status === "error" && (
          <>
            <XCircle className="mx-auto text-[hsl(var(--danger))]" size={56} />
            <h1 className="font-serif text-2xl mt-5">{t("verify_email.title_error", "Линкът е невалиден")}</h1>
            <p className="mt-3 text-sm text-[hsl(var(--ink-muted))]" data-testid="verify-email-error">
              {message}
            </p>
            <Link to="/dashboard" className="btn btn-secondary mt-6 inline-block">
              {t("verify_email.go_dashboard", "Към профила")}
            </Link>
          </>
        )}
      </div>
    </main>
  );
}
