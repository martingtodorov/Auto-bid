import React, { useState } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { ShieldCheck, ArrowLeft } from "lucide-react";
import { useAuth, formatError } from "../lib/auth";

export default function LoginPage() {
  const { login, verifyTwoFactor } = useAuth();
  const navigate = useNavigate();
  const loc = useLocation();
  const next = new URLSearchParams(loc.search).get("next") || "/";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");

  // 2FA stage
  const [challenge, setChallenge] = useState(null);
  const [code, setCode] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    setErr(""); setLoading(true);
    try {
      const res = await login(email, password);
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
            <ArrowLeft size={14} /> Обратно
          </button>
          <div className="overline text-[hsl(var(--accent))] flex items-center gap-2">
            <ShieldCheck size={14} /> Двуфакторна автентикация
          </div>
          <h1 className="font-serif text-4xl mt-3">Въведете код</h1>
          <p className="mt-3 text-sm text-[hsl(var(--ink-muted))]">Отворете вашето authenticator приложение (Google Authenticator, Authy…) и въведете 6-цифрения код. Ако нямате достъп до устройството си, можете да използвате резервен код.</p>

          <form onSubmit={submit2FA} className="mt-8 space-y-5">
            <div>
              <label className="overline text-[hsl(var(--ink-muted))] block mb-2">Код</label>
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
              {loading ? "Проверка…" : "Потвърди"}
            </button>
          </form>
        </div>
      </main>
    );
  }

  return (
    <main className="py-20" data-testid="login-page">
      <div className="max-w-md mx-auto px-6">
        <div className="overline text-[hsl(var(--accent))]">Акаунт</div>
        <h1 className="font-serif text-4xl mt-3">Добре дошли отново</h1>
        <p className="mt-3 text-sm text-[hsl(var(--ink-muted))]">Влезте, за да наддавате, коментирате и следите търгове.</p>

        <form onSubmit={submit} className="mt-10 space-y-5">
          <div>
            <label className="overline text-[hsl(var(--ink-muted))] block mb-2">Имейл</label>
            <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className="w-full border border-[hsl(var(--line))] h-12 px-3" data-testid="login-email" />
          </div>
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="overline text-[hsl(var(--ink-muted))]">Парола</label>
              <Link to="/forgot-password" className="text-xs text-[hsl(var(--accent))] hover:underline" data-testid="login-forgot-link">
                Забравена парола?
              </Link>
            </div>
            <input type="password" required value={password} onChange={(e) => setPassword(e.target.value)} className="w-full border border-[hsl(var(--line))] h-12 px-3" data-testid="login-password" />
          </div>
          {err && <p className="text-sm text-[hsl(var(--danger))]" data-testid="login-error">{err}</p>}
          <button type="submit" disabled={loading} className="btn btn-primary w-full" data-testid="login-submit">
            {loading ? "Влизане…" : "Вход"}
          </button>
        </form>

        <p className="mt-8 text-sm text-[hsl(var(--ink-muted))]">
          Нямате акаунт? <Link to="/register" className="underline text-[hsl(var(--ink))]">Регистрация</Link>
        </p>
      </div>
    </main>
  );
}
