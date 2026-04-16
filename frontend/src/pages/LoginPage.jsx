import React, { useState } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { useAuth, formatError } from "../lib/auth";

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const loc = useLocation();
  const next = new URLSearchParams(loc.search).get("next") || "/";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    setErr(""); setLoading(true);
    try {
      await login(email, password);
      navigate(next);
    } catch (e) { setErr(formatError(e)); }
    finally { setLoading(false); }
  };

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
            <label className="overline text-[hsl(var(--ink-muted))] block mb-2">Парола</label>
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
