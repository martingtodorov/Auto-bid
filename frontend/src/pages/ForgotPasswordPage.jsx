import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Mail, Check } from "lucide-react";
import { api } from "../lib/apiClient";
import { formatError } from "../lib/auth";

export default function ForgotPasswordPage() {
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [password2, setPassword2] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");

  const requestCode = async (e) => {
    e.preventDefault();
    setErr(""); setLoading(true);
    try {
      const { data } = await api.post("/auth/forgot-password", { email: email.trim().toLowerCase() });
      setMsg(data.message || "Ако акаунтът съществува, код е изпратен.");
      setStep(2);
    } catch (e) { setErr(formatError(e)); }
    finally { setLoading(false); }
  };

  const resetPw = async (e) => {
    e.preventDefault();
    if (password !== password2) { setErr("Паролите не съвпадат"); return; }
    if (password.length < 6) { setErr("Паролата трябва да е поне 6 символа"); return; }
    setErr(""); setLoading(true);
    try {
      await api.post("/auth/reset-password", { email: email.trim().toLowerCase(), code: code.trim(), new_password: password });
      setStep(3);
      setTimeout(() => navigate("/login"), 3500);
    } catch (e) { setErr(formatError(e)); }
    finally { setLoading(false); }
  };

  return (
    <main className="py-20" data-testid="forgot-password-page">
      <div className="max-w-md mx-auto px-6">
        <div className="overline text-[hsl(var(--accent))]">Възстановяване</div>
        <h1 className="font-serif text-4xl mt-3">
          {step === 1 ? "Забравена парола" : step === 2 ? "Въведете кода" : "Готово"}
        </h1>

        {step === 1 && (
          <>
            <p className="mt-3 text-sm text-[hsl(var(--ink-muted))]">Въведете имейла на акаунта си и ще получите 6-цифрен код за нулиране.</p>
            <form onSubmit={requestCode} className="mt-8 space-y-5">
              <div>
                <label className="overline text-[hsl(var(--ink-muted))] block mb-2">Имейл</label>
                <input type="email" required autoFocus value={email} onChange={(e) => setEmail(e.target.value)} className="w-full border border-[hsl(var(--line))] h-12 px-3" data-testid="forgot-email" />
              </div>
              {err && <p className="text-sm text-[hsl(var(--danger))]" data-testid="forgot-error">{err}</p>}
              <button type="submit" disabled={loading} className="btn btn-primary w-full" data-testid="forgot-submit">
                {loading ? "Изпращане…" : "Изпрати код"}
              </button>
            </form>
          </>
        )}

        {step === 2 && (
          <>
            <div className="mt-4 p-4 rounded-card bg-[hsl(var(--surface))] border border-[hsl(var(--line))] flex items-start gap-3">
              <Mail size={16} className="text-[hsl(var(--accent))] mt-0.5" />
              <div className="text-sm">{msg}</div>
            </div>
            <form onSubmit={resetPw} className="mt-6 space-y-5">
              <div>
                <label className="overline text-[hsl(var(--ink-muted))] block mb-2">Код от имейла</label>
                <input type="text" inputMode="numeric" required maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} className="w-full border border-[hsl(var(--line))] h-14 px-4 text-2xl tracking-[0.4em] text-center font-mono" placeholder="000000" data-testid="forgot-code" />
              </div>
              <div>
                <label className="overline text-[hsl(var(--ink-muted))] block mb-2">Нова парола</label>
                <input type="password" required minLength={6} value={password} onChange={(e) => setPassword(e.target.value)} className="w-full border border-[hsl(var(--line))] h-12 px-3" data-testid="forgot-new-password" />
              </div>
              <div>
                <label className="overline text-[hsl(var(--ink-muted))] block mb-2">Потвърди паролата</label>
                <input type="password" required minLength={6} value={password2} onChange={(e) => setPassword2(e.target.value)} className="w-full border border-[hsl(var(--line))] h-12 px-3" data-testid="forgot-new-password-2" />
              </div>
              {err && <p className="text-sm text-[hsl(var(--danger))]" data-testid="forgot-error">{err}</p>}
              <button type="submit" disabled={loading} className="btn btn-primary w-full" data-testid="forgot-reset-submit">
                {loading ? "Обновяване…" : "Смени паролата"}
              </button>
              <button type="button" onClick={() => { setStep(1); setCode(""); setPassword(""); setPassword2(""); setErr(""); }} className="text-sm text-[hsl(var(--ink-muted))] hover:text-[hsl(var(--ink))] block mx-auto">
                Върни се за нов код
              </button>
            </form>
          </>
        )}

        {step === 3 && (
          <div className="mt-8 p-8 rounded-card border border-[hsl(var(--accent))] bg-white text-center" data-testid="forgot-success">
            <div className="mx-auto w-12 h-12 rounded-full bg-[hsl(var(--accent))] text-white flex items-center justify-center">
              <Check size={22} />
            </div>
            <h2 className="font-serif text-2xl mt-4">Паролата е сменена!</h2>
            <p className="mt-2 text-sm text-[hsl(var(--ink-muted))]">Пренасочваме ви към входа…</p>
          </div>
        )}

        <p className="mt-8 text-sm text-[hsl(var(--ink-muted))]">
          <Link to="/login" className="underline text-[hsl(var(--ink))]">← Обратно към вход</Link>
        </p>
      </div>
    </main>
  );
}
