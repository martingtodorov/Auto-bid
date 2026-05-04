/**
 * SsoStartPage — рендерира се САМО на канонизичния домейн (autoandbid.com).
 *
 * Flow:
 *   1. URL съдържа `?return_to=https://autoandbid.bg/some/path`.
 *   2. Извикваме POST /api/auth/sso/issue с return_to.
 *      • 401 → потребителят не е логнат на .com → редиректваме го
 *        обратно към return_to с `?sso_denied=1` (вместо да го заключим).
 *      • 200 → получаваме `nonce`. Редиректваме към
 *        `<target_origin>/auth/sso/callback?token=<nonce>` + return_to.
 *   3. Потребителят вижда едноекранен splash "Authenticating…",
 *      browser-ът прави един full-page redirect напред.
 */
import React, { useEffect, useState } from "react";
import { api } from "../lib/apiClient";
import { useTranslation } from "react-i18next";

const ALLOWED_HOSTS = [
  "https://autoandbid.com", "https://www.autoandbid.com",
  "https://autoandbid.bg", "https://www.autoandbid.bg",
  "https://autoandbid.ro", "https://www.autoandbid.ro",
];

function isAllowedReturnTo(url) {
  if (!url) return false;
  try {
    const u = new URL(url);
    const origin = `${u.protocol}//${u.host}`;
    if (ALLOWED_HOSTS.includes(origin)) return true;
    // Dev preview hosts
    if (/\.preview\.emergentagent\.com$/i.test(u.hostname)) return true;
    if (u.hostname === "localhost" || u.hostname === "127.0.0.1") return true;
  } catch { /* ignore */ }
  return false;
}

export default function SsoStartPage() {
  const { t } = useTranslation();
  const [error, setError] = useState("");

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const returnTo = params.get("return_to") || "";
    if (!isAllowedReturnTo(returnTo)) {
      setError(t("sso.bad_return_to", "Невалиден целеви домейн."));
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const { data } = await api.post("/auth/sso/issue", { return_to: returnTo });
        if (cancelled) return;
        // Bounce browser to the receiving domain's callback. The
        // nonce is in the URL — single-use, 60 s TTL.
        const u = new URL(returnTo);
        const cb = `${u.protocol}//${u.host}/auth/sso/callback?token=${encodeURIComponent(data.nonce)}&return_to=${encodeURIComponent(returnTo)}`;
        window.location.replace(cb);
      } catch (e) {
        // 401 → anonymous on .com. Send the user back to where they
        // came from with an `?sso_denied=1` marker; the bootstrap
        // there will respect the marker and stop bouncing.
        const status = e?.response?.status;
        if (status === 401) {
          const sep = returnTo.includes("?") ? "&" : "?";
          window.location.replace(`${returnTo}${sep}sso_denied=1`);
        } else {
          setError(t("sso.issue_failed", "Неуспешна обработка на SSO заявката."));
        }
      }
    })();
    return () => { cancelled = true; };
  }, [t]);

  return (
    <div className="min-h-screen flex items-center justify-center" data-testid="sso-start-page">
      <div className="text-center max-w-md p-8">
        {error ? (
          <p className="text-red-600">{error}</p>
        ) : (
          <>
            <div className="w-10 h-10 mx-auto mb-4 rounded-full border-2 border-[hsl(var(--accent))] border-t-transparent animate-spin" />
            <p className="text-sm text-[hsl(var(--ink-muted))]">
              {t("sso.authenticating", "Влизаме в акаунта ви…")}
            </p>
          </>
        )}
      </div>
    </div>
  );
}
