import React, { useEffect, useState } from "react";
import { useSearchParams, Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { CheckCircle2, XCircle, Loader2, Fingerprint, Check } from "lucide-react";
import { api } from "../lib/apiClient";
import { useAuth } from "../lib/auth";
import { isPasskeySupported, registerPasskey, verifyReauth } from "../lib/passkey";

/**
 * Email verification landing page.
 * Reads ?token=... from the URL, POSTs it to /api/auth/verify-email and
 * shows success / error state. On success, refreshes auth state so any
 * gated UI immediately becomes available, then offers a one-click
 * "Add passkey" upgrade (skippable).
 */
export default function VerifyEmailPage() {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { user, refresh } = useAuth();
  const token = params.get("token");
  const [status, setStatus] = useState("loading"); // loading | ok | error
  const [message, setMessage] = useState("");

  // Passkey enrollment (success-state only)
  const passkeySupported = isPasskeySupported();
  const [passkeyState, setPasskeyState] = useState("idle"); // idle | reauth | adding | done | error
  const [passkeyErr, setPasskeyErr] = useState("");
  const [reauthPwd, setReauthPwd] = useState("");

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

  const enrollPasskey = async () => {
    setPasskeyErr(""); setPasskeyState("adding");
    try {
      await registerPasskey();
      setPasskeyState("done");
    } catch (e) {
      // 401 + X-Reauth-Required → ask for password, then retry once.
      const needsReauth = e?.response?.status === 401 || /reauth/i.test(e?.message || "");
      if (needsReauth) {
        setPasskeyState("reauth");
        return;
      }
      setPasskeyErr(e?.message || t("verify_email.passkey_error", "Регистрацията на passkey се провали."));
      setPasskeyState("error");
    }
  };

  const submitReauth = async (e) => {
    e.preventDefault();
    setPasskeyErr(""); setPasskeyState("adding");
    try {
      await verifyReauth(reauthPwd);
      setReauthPwd("");
      await registerPasskey();
      setPasskeyState("done");
    } catch (e) {
      setPasskeyErr(e?.response?.data?.detail || e?.message || t("verify_email.passkey_error", "Грешка."));
      setPasskeyState("reauth");
    }
  };

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

            {/* Passkey upgrade — only shown when the device supports it,
                the user is signed in (so we can call register-begin), and
                they haven't completed enrollment yet on this screen. */}
            {passkeySupported && user && passkeyState !== "done" && (
              <div className="mt-8 text-left rounded-card border border-[hsl(var(--line))] p-5 bg-[hsl(var(--surface))]" data-testid="verify-email-passkey-card">
                <div className="flex items-start gap-3">
                  <div className="shrink-0 h-10 w-10 rounded-full bg-[hsl(var(--accent))]/10 flex items-center justify-center">
                    <Fingerprint size={20} className="text-[hsl(var(--accent))]" />
                  </div>
                  <div className="flex-1">
                    <div className="font-semibold">{t("verify_email.passkey_title", "Добави passkey")}</div>
                    <p className="mt-1 text-xs text-[hsl(var(--ink-muted))] leading-relaxed">
                      {t("verify_email.passkey_subtitle", "Влизай без парола — с пръстов отпечатък, Face ID или PIN на устройството.")}
                    </p>
                  </div>
                </div>

                {passkeyState === "reauth" && (
                  <form onSubmit={submitReauth} className="mt-4 space-y-3">
                    <label className="overline text-[hsl(var(--ink-muted))] block">
                      {t("verify_email.reauth_label", "Потвърди паролата си")}
                    </label>
                    <input
                      type="password"
                      autoFocus
                      required
                      value={reauthPwd}
                      onChange={(e) => setReauthPwd(e.target.value)}
                      autoComplete="current-password"
                      className="w-full border border-[hsl(var(--line))] h-11 px-3"
                      data-testid="verify-email-passkey-reauth"
                    />
                    {passkeyErr && (
                      <p className="text-xs text-[hsl(var(--danger))]">{passkeyErr}</p>
                    )}
                    <button
                      type="submit"
                      className="btn btn-primary w-full inline-flex items-center justify-center gap-2"
                      data-testid="verify-email-passkey-reauth-submit"
                    >
                      <Fingerprint size={16} />
                      {t("verify_email.passkey_continue", "Продължи към passkey")}
                    </button>
                  </form>
                )}

                {passkeyState !== "reauth" && (
                  <button
                    type="button"
                    onClick={enrollPasskey}
                    disabled={passkeyState === "adding"}
                    className="btn btn-primary w-full mt-4 inline-flex items-center justify-center gap-2"
                    data-testid="verify-email-add-passkey"
                  >
                    <Fingerprint size={16} />
                    {passkeyState === "adding"
                      ? t("verify_email.passkey_adding", "Добавяне…")
                      : t("verify_email.passkey_add_cta", "Добави passkey")}
                  </button>
                )}

                {passkeyState === "error" && passkeyErr && (
                  <p className="mt-2 text-xs text-[hsl(var(--danger))]" data-testid="verify-email-passkey-error">
                    {passkeyErr}
                  </p>
                )}
              </div>
            )}

            {passkeyState === "done" && (
              <div className="mt-6 inline-flex items-center gap-2 text-sm text-[hsl(var(--accent))]" data-testid="verify-email-passkey-done">
                <Check size={16} />
                {t("verify_email.passkey_done", "Passkey е добавен успешно.")}
              </div>
            )}

            <button
              onClick={() => navigate("/dashboard")}
              className={`${passkeySupported && user && passkeyState !== "done" ? "btn btn-secondary" : "btn btn-primary"} mt-6`}
              data-testid="verify-email-go-dashboard"
            >
              {passkeySupported && user && passkeyState !== "done"
                ? t("verify_email.skip_passkey", "Пропусни — към профила")
                : t("verify_email.go_dashboard", "Към профила")}
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
