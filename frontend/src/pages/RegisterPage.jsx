import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth, formatError } from "../lib/auth";

export default function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    setErr(""); setLoading(true);
    try {
      await register(email, password, name);
      navigate("/");
    } catch (e) { setErr(formatError(e)); }
    finally { setLoading(false); }
  };

  return (
    <main className="py-20" data-testid="register-page">
      <div className="max-w-md mx-auto px-6">
        <div className="overline text-[hsl(var(--accent))]">Нов акаунт</div>
        <h1 className="font-serif text-4xl mt-3">Присъединете се</h1>
        <p className="mt-3 text-sm text-[hsl(var(--ink-muted))]">Безплатна регистрация. Започнете да наддавате днес.</p>

        <form onSubmit={submit} className="mt-10 space-y-5">
          <div>
            <label className="overline text-[hsl(var(--ink-muted))] block mb-2">Име</label>
            <input required value={name} onChange={(e) => setName(e.target.value)} className="w-full border border-[hsl(var(--line))] h-12 px-3" data-testid="register-name" />
          </div>
          <div>
            <label className="overline text-[hsl(var(--ink-muted))] block mb-2">Имейл</label>
            <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className="w-full border border-[hsl(var(--line))] h-12 px-3" data-testid="register-email" />
          </div>
          <div>
            <label className="overline text-[hsl(var(--ink-muted))] block mb-2">Парола (мин. 6 символа)</label>
            <input type="password" required minLength={6} value={password} onChange={(e) => setPassword(e.target.value)} className="w-full border border-[hsl(var(--line))] h-12 px-3" data-testid="register-password" />
          </div>
          {err && <p className="text-sm text-[hsl(var(--danger))]" data-testid="register-error">{err}</p>}
          <button type="submit" disabled={loading} className="btn btn-primary w-full" data-testid="register-submit">
            {loading ? "Регистрация…" : "Създай акаунт"}
          </button>
        </form>

        <p className="mt-8 text-sm text-[hsl(var(--ink-muted))]">
          Имате акаунт? <Link to="/login" className="underline text-[hsl(var(--ink))]">Вход</Link>
        </p>
      </div>
    </main>
  );
}
