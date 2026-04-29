import React, { useState } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { ShieldCheck, ArrowLeft } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useAuth, formatError } from "../lib/auth";

export default function LoginPage() {
  const { t } = useTranslation();
  const { login, verifyTwoFactor } = useAuth();
  const navigate = useNavigate();
  const loc = useLocation();
  const next = new URLSearchParams(loc.search).get("next") || "/";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(false);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");

  // 2FA stage
  const [challenge, setChallenge] = useState(null);
  const [code, setCode] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    setErr(""); setLoading(true);
    try {
      const res = await login(email, password, remember);
      if (res?.requires_2fa) {
        setChallenge(res.challenge_token);
      } else {
        navigate(next);
      }
    } catch (e) { setErr(formatError(e)); }
    finally { setLoading(false); }
  };

  const submit2FA = async (e) => {
    e.preventDefault();
    setErr(""); setLoading(true);
    try {
      await verifyTwoFactor(challenge, code.trim());
      navigate(next);
    } catch (e) { setErr(formatError(e)); }
    finally { setLoading(false); }
  };

  if (challenge) {
    return (
      <main className="py-20" data-testid="login-page">
        <div className="max-w-md mx-auto px-6">
          <button onClick={() => { setChallenge(null); setCode(""); setErr(""); }} className="text-sm text-[hsl(var(--ink-muted))] inline-flex items-center gap-1.5 mb-6 hover:text-[hsl(var(--ink))]" data-testid="login-2fa-back">
            <ArrowLeft size={14} /> {t("forms.back")}
          </button>
          <div className="overline text-[hsl(var(--accent))] flex items-center gap-2">
            <ShieldCheck size={14} /> {t("auth.two_fa_title")}
          </div>
          <h1 className="font-serif text-4xl mt-3">{t("auth.two_fa_enter_title") || "Въведете код"}</h1>
          <p className="mt-3 text-sm text-[hsl(var(--ink-muted))]">{t("auth.two_fa_enter_code")}</p>

          <form onSubmit={submit2FA} className="mt-8 space-y-5">
            <div>
              <label className="overline text-[hsl(var(--ink-muted))] block mb-2">{t("auth.two_fa_code_label") || "Код"}</label>
              <input
                type="text"
                inputMode="numeric"
                autoFocus
                required
                value={code}
                onChange={(e) => setCode(e.target.value)}
                maxLength={8}
                className="w-full border border-[hsl(var(--line))] h-14 px-4 text-2xl tracking-[0.4em] text-center font-mono"
                placeholder="000000"
                data-testid="login-2fa-code"
              />
            </div>
            {err && <p className="text-sm text-[hsl(var(--danger))]" data-testid="login-error">{err}</p>}
            <button type="submit" disabled={loading || code.length < 6} className="btn btn-primary w-full" data-testid="login-2fa-submit">
              {loading ? (t("auth.two_fa_verifying") || "Проверка…") : t("auth.two_fa_verify")}
            </button>
          </form>
        </div>
      </main>
    );
  }

  return (
    <main className="py-20" data-testid="login-page">
      <div className="max-w-md mx-auto px-6">
        <div className="overline text-[hsl(var(--accent))]">{t("auth.account") || "Акаунт"}</div>
        <h1 className="font-serif text-4xl mt-3">{t("auth.welcome_back")}</h1>
        <p className="mt-3 text-sm text-[hsl(var(--ink-muted))]">{t("auth.login_subtitle")}</p>

        <form onSubmit={submit} className="mt-10 space-y-5">
          <div>
            <label className="overline text-[hsl(var(--ink-muted))] block mb-2">{t("forms.email")}</label>
            <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className="w-full border border-[hsl(var(--line))] h-12 px-3" data-testid="login-email" />
          </div>
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="overline text-[hsl(var(--ink-muted))]">{t("forms.password")}</label>
              <Link to="/forgot-password" className="text-xs text-[hsl(var(--accent))] hover:underline" data-testid="login-forgot-link">
                {t("forms.forgot_password")}
              </Link>
            </div>
            <input type="password" required value={password} onChange={(e) => setPassword(e.target.value)} className="w-full border border-[hsl(var(--line))] h-12 px-3" data-testid="login-password" />
          </div>
          <label className="flex items-center gap-2 text-sm text-[hsl(var(--ink-muted))] select-none cursor-pointer" data-testid="login-remember-label">
            <input
              type="checkbox"
              checked={remember}
              onChange={(e) => setRemember(e.target.checked)}
              className="h-4 w-4 accent-[hsl(var(--accent))] cursor-pointer"
              data-testid="login-remember"
            />
            <span>{t("auth.remember_me")}</span>
          </label>
          {err && <p className="text-sm text-[hsl(var(--danger))]" data-testid="login-error">{err}</p>}
          <button type="submit" disabled={loading} className="btn btn-primary w-full" data-testid="login-submit">
            {loading ? (t("auth.signing_in") || "Влизане…") : t("nav.login")}
          </button>
        </form>

        <p className="mt-8 text-sm text-[hsl(var(--ink-muted))]">
          {t("auth.no_account")} <Link to="/register" className="underline text-[hsl(var(--ink))]" data-testid="login-to-register">{t("nav.register")}</Link>
        </p>
      </div>
    </main>
  );
}
