import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth, formatError } from "../lib/auth";
import PasswordStrengthHint from "../components/PasswordStrengthHint";

export default function RegisterPage() {
  const { t } = useTranslation();
  const { register } = useAuth();
  const navigate = useNavigate();
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [username, setUsername] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
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
      await register({
        email,
        password,
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        username: username.trim(),
        phone: phone.trim(),
        terms_accepted: termsAccepted,
      });
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
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="overline text-[hsl(var(--ink-muted))] block mb-2">
                {t("forms.first_name") || "Име"}
              </label>
              <input
                required
                value={firstName}
                onChange={(e) => setFirstName(e.target.value)}
                className="w-full border border-[hsl(var(--line))] h-12 px-3"
                data-testid="register-first-name"
                autoComplete="given-name"
              />
            </div>
            <div>
              <label className="overline text-[hsl(var(--ink-muted))] block mb-2">
                {t("forms.last_name") || "Фамилия"}
              </label>
              <input
                required
                value={lastName}
                onChange={(e) => setLastName(e.target.value)}
                className="w-full border border-[hsl(var(--line))] h-12 px-3"
                data-testid="register-last-name"
                autoComplete="family-name"
              />
            </div>
          </div>
          <div>
            <label className="overline text-[hsl(var(--ink-muted))] block mb-2">
              {t("forms.username") || "Потребителско име"}
            </label>
            <input
              required
              minLength={3}
              maxLength={30}
              pattern="[A-Za-z0-9_.\-]{3,30}"
              title={t("forms.username_rules") || "3–30 знака: латински букви, цифри, . _ -"}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full border border-[hsl(var(--line))] h-12 px-3"
              data-testid="register-username"
              autoComplete="username"
            />
          </div>
          <div>
            <label className="overline text-[hsl(var(--ink-muted))] block mb-2">
              {t("forms.phone") || "Телефон"}
            </label>
            <input
              type="tel"
              required
              placeholder="+359..."
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              className="w-full border border-[hsl(var(--line))] h-12 px-3"
              data-testid="register-phone"
              autoComplete="tel"
            />
          </div>
          <div>
            <label className="overline text-[hsl(var(--ink-muted))] block mb-2">{t("forms.email")}</label>
            <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className="w-full border border-[hsl(var(--line))] h-12 px-3" data-testid="register-email" autoComplete="email" />
          </div>
          <div>
            <label className="overline text-[hsl(var(--ink-muted))] block mb-2">
              {t("forms.password")}
            </label>
            <input
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full border border-[hsl(var(--line))] h-12 px-3"
              data-testid="register-password"
              autoComplete="new-password"
            />
            <PasswordStrengthHint password={password} />
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
