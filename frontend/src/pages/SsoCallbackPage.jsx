/**
 * SsoCallbackPage — рендерира се на receiving домейна (.bg / .ro).
 *
 * 1. Чете `?token=<nonce>` от URL.
 * 2. Изпраща POST /api/auth/sso/consume → backend сетва auth cookie.
 * 3. Прави `history.replaceState` за да изчисти token-а от URL-а
 *    (security hygiene + клиниране на shareable links).
 * 4. Редиректва към `return_to` (already validated server-side).
 *
 * При грешка: показваме съобщение + бутон към login страницата.
 */
import React, { useEffect, useState } from "react";
import { api } from "../lib/apiClient";
import { useAuth } from "../lib/auth";
import { useTranslation } from "react-i18next";

export default function SsoCallbackPage() {
  const { t } = useTranslation();
  const { setUser } = useAuth();
  const [error, setError] = useState("");

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const token = params.get("token") || "";
    const returnTo = params.get("return_to") || "/";
    if (!token) {
      setError(t("sso.missing_token", "Липсва токен."));
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const { data } = await api.post("/auth/sso/consume", { nonce: token });
        if (cancelled) return;
        // Update React state — auth cookie is already set by the
        // backend response. We also blow away the URL token via
        // replaceState so it doesn't leak into history / analytics.
        if (data.user) setUser(data.user);
        try { window.history.replaceState({}, "", "/"); } catch { /* ignore */ }
        // Resolve the path of the original return_to and navigate.
        let dest = "/";
        try {
          const u = new URL(returnTo);
          dest = u.pathname + (u.search || "") + (u.hash || "");
        } catch { /* fall back to root */ }
        window.location.replace(dest);
      } catch (e) {
        const status = e?.response?.status;
        if (status === 401) {
          setError(t("sso.token_invalid", "Сесията е изтекла. Моля, влезте отново."));
        } else {
          setError(t("sso.consume_failed", "Неуспешна автентикация."));
        }
      }
    })();
    return () => { cancelled = true; };
  }, [t, setUser]);

  return (
    <div className="min-h-screen flex items-center justify-center" data-testid="sso-callback-page">
      <div className="text-center max-w-md p-8">
        {error ? (
          <>
            <p className="text-red-600 mb-4">{error}</p>
            <a href="/login" className="btn btn-primary" data-testid="sso-login-fallback">
              {t("sso.login_cta", "Към входа")}
            </a>
          </>
        ) : (
          <>
            <div className="w-10 h-10 mx-auto mb-4 rounded-full border-2 border-[hsl(var(--accent))] border-t-transparent animate-spin" />
            <p className="text-sm text-[hsl(var(--ink-muted))]">
              {t("sso.completing", "Подготвяме сесията ви…")}
            </p>
          </>
        )}
      </div>
    </div>
  );
}
