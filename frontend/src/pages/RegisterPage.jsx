import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth, formatError } from "../lib/auth";

export default function RegisterPage() {
  const { t } = useTranslation();
  const { register } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [termsAccepted, setTermsAccepted] = useState(false);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    setErr("");
    if (!termsAccepted) {
      setErr(t("auth.terms_required") || "Моля, приемете Общите условия, за да продължите.");
      return;
    }
    setLoading(true);
    try {
      await register(email, password, name, termsAccepted);
      navigate("/");
    } catch (e) { setErr(formatError(e)); }
    finally { setLoading(false); }
  };

  return (
    <main className="py-20" data-testid="register-page">
      <div className="max-w-md mx-auto px-6">
        <div className="overline text-[hsl(var(--accent))]">{t("auth.new_account") || "Нов акаунт"}</div>
        <h1 className="font-serif text-4xl mt-3">{t("auth.join_us") || "Присъединете се"}</h1>
        <p className="mt-3 text-sm text-[hsl(var(--ink-muted))]">
          {t("auth.register_subtitle") || "Безплатна регистрация. Започнете да наддавате днес."}
        </p>

        <form onSubmit={submit} className="mt-10 space-y-5">
          <div>
            <label className="overline text-[hsl(var(--ink-muted))] block mb-2">{t("forms.name")}</label>
            <input required value={name} onChange={(e) => setName(e.target.value)} className="w-full border border-[hsl(var(--line))] h-12 px-3" data-testid="register-name" />
          </div>
          <div>
            <label className="overline text-[hsl(var(--ink-muted))] block mb-2">{t("forms.email")}</label>
            <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className="w-full border border-[hsl(var(--line))] h-12 px-3" data-testid="register-email" />
          </div>
          <div>
            <label className="overline text-[hsl(var(--ink-muted))] block mb-2">
              {t("forms.password")} ({t("auth.min_6_chars") || "мин. 6 символа"})
            </label>
            <input type="password" required minLength={6} value={password} onChange={(e) => setPassword(e.target.value)} className="w-full border border-[hsl(var(--line))] h-12 px-3" data-testid="register-password" />
          </div>

          {/* Terms & Conditions consent — records IP/UA/timestamp on the server */}
          <label
            className="flex items-start gap-3 cursor-pointer select-none rounded-card border border-[hsl(var(--line))] p-3 hover:border-[hsl(var(--accent))]/60 transition-colors"
            data-testid="register-terms-label"
          >
            <input
              type="checkbox"
              checked={termsAccepted}
              onChange={(e) => setTermsAccepted(e.target.checked)}
              className="mt-1 h-4 w-4 shrink-0 accent-[hsl(var(--accent))]"
              data-testid="register-terms-checkbox"
              required
            />
            <span className="text-xs leading-relaxed text-[hsl(var(--ink-muted))]">
              {t("auth.agree_terms_prefix")}{" "}
              <Link to="/terms" target="_blank" className="underline text-[hsl(var(--ink))]" data-testid="register-terms-link">
                {t("auth.terms_link")}
              </Link>{" "}
              {t("auth.and")}{" "}
              <Link to="/terms#privacy" target="_blank" className="underline text-[hsl(var(--ink))]" data-testid="register-privacy-link">
                {t("auth.privacy_link")}
              </Link>
              .
            </span>
          </label>

          {err && <p className="text-sm text-[hsl(var(--danger))]" data-testid="register-error">{err}</p>}
          <button
            type="submit"
            disabled={loading || !termsAccepted}
            className="btn btn-primary w-full disabled:opacity-50 disabled:cursor-not-allowed"
            data-testid="register-submit"
          >
            {loading ? (t("forms.loading") || "Регистрация…") : (t("auth.create_account") || "Създай акаунт")}
          </button>
        </form>

        <p className="mt-8 text-sm text-[hsl(var(--ink-muted))]">
          {t("auth.have_account")} <Link to="/login" className="underline text-[hsl(var(--ink))]" data-testid="register-to-login">{t("nav.login")}</Link>
        </p>
      </div>
    </main>
  );
}
