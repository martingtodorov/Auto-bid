import React, { useState } from "react";
import { ShieldCheck, ShieldOff, Copy, Check } from "lucide-react";
import { api } from "../lib/apiClient";
import { formatError, useAuth } from "../lib/auth";

export default function TwoFactorSection() {
  const { user, refresh } = useAuth();
  const enabled = !!user?.totp_enabled;

  const [provisioning, setProvisioning] = useState(null); // { secret, qr_code_data_url, otpauth_uri }
  const [code, setCode] = useState("");
  const [backupCodes, setBackupCodes] = useState(null);
  const [disableCode, setDisableCode] = useState("");
  const [showDisable, setShowDisable] = useState(false);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const [copied, setCopied] = useState(false);

  const start = async () => {
    setErr(""); setLoading(true);
    try {
      const { data } = await api.post("/auth/2fa/enable");
      setProvisioning(data);
    } catch (e) { setErr(formatError(e)); }
    finally { setLoading(false); }
  };

  const confirm = async (e) => {
    e.preventDefault();
    setErr(""); setLoading(true);
    try {
      const { data } = await api.post("/auth/2fa/confirm", { code: code.trim() });
      setBackupCodes(data.backup_codes || []);
      setProvisioning(null);
      setCode("");
      await refresh();
    } catch (e) { setErr(formatError(e)); }
    finally { setLoading(false); }
  };

  const disable = async (e) => {
    e.preventDefault();
    setErr(""); setLoading(true);
    try {
      await api.post("/auth/2fa/disable", { code: disableCode.trim() });
      setShowDisable(false);
      setDisableCode("");
      await refresh();
    } catch (e) { setErr(formatError(e)); }
    finally { setLoading(false); }
  };

  const copySecret = () => {
    if (provisioning?.secret) {
      navigator.clipboard.writeText(provisioning.secret);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    }
  };

  return (
    <section className="mt-8 rounded-card border border-[hsl(var(--line))] bg-white p-6 lg:p-8" data-testid="twofa-section">
      <div className="flex items-center gap-3">
        {enabled ? <ShieldCheck size={18} className="text-[hsl(var(--accent))]" /> : <ShieldOff size={18} className="text-[hsl(var(--ink-muted))]" />}
        <h2 className="font-serif text-2xl">Двуфакторна автентикация (2FA)</h2>
        {enabled && <span className="text-xs px-2 py-0.5 bg-[hsl(var(--accent))] text-white rounded-full">Активна</span>}
      </div>
      <p className="mt-3 text-sm text-[hsl(var(--ink-muted))]">
        Защитете акаунта си с 6-цифрен код, генериран от authenticator приложение (Google Authenticator, Authy, 1Password).
      </p>

      {/* Backup codes after confirm */}
      {backupCodes && (
        <div className="mt-6 rounded-card border-2 border-amber-500 bg-amber-50 p-5" data-testid="backup-codes-display">
          <h3 className="font-semibold">Запазете вашите резервни кодове</h3>
          <p className="text-sm mt-1 text-[hsl(var(--ink-muted))]">Всеки код може да се използва еднократно при загубен достъп до authenticator. Съхранявайте ги на сигурно място.</p>
          <div className="mt-4 grid grid-cols-2 gap-2 font-mono text-sm bg-white p-4 rounded-card border border-amber-300">
            {backupCodes.map((c) => <div key={c} className="tracking-wider text-center py-1">{c}</div>)}
          </div>
          <button onClick={() => { navigator.clipboard.writeText(backupCodes.join("\n")); setCopied(true); setTimeout(() => setCopied(false), 1500); }} className="mt-3 text-sm text-[hsl(var(--accent))] inline-flex items-center gap-1.5 hover:underline">
            {copied ? <><Check size={14} /> Копирано</> : <><Copy size={14} /> Копирай всички</>}
          </button>
          <button onClick={() => setBackupCodes(null)} className="mt-3 ml-6 text-sm underline text-[hsl(var(--ink-muted))]">Затвори</button>
        </div>
      )}

      {/* Provisioning (QR code + verify) */}
      {provisioning && (
        <div className="mt-6 rounded-card border border-[hsl(var(--line))] bg-[hsl(var(--surface))] p-5" data-testid="twofa-provisioning">
          <h3 className="font-semibold">Сканирайте QR кода</h3>
          <p className="text-sm mt-1 text-[hsl(var(--ink-muted))]">Отворете authenticator приложение и сканирайте кода, или въведете тайния ключ ръчно.</p>
          <div className="mt-4 flex gap-6 items-start flex-wrap">
            <img src={provisioning.qr_code_data_url} alt="2FA QR код" className="w-44 h-44 bg-white p-2 rounded-card border border-[hsl(var(--line))]" data-testid="twofa-qr" />
            <div className="flex-1 min-w-[240px]">
              <div className="overline text-[hsl(var(--ink-muted))] mb-1">Ръчен ключ</div>
              <div className="flex gap-2">
                <code className="text-xs bg-white px-3 py-2 rounded-card border border-[hsl(var(--line))] break-all flex-1 font-mono" data-testid="twofa-secret">{provisioning.secret}</code>
                <button onClick={copySecret} className="px-3 rounded-card border border-[hsl(var(--line))] bg-white hover:bg-[hsl(var(--surface))]">
                  {copied ? <Check size={14} /> : <Copy size={14} />}
                </button>
              </div>
            </div>
          </div>
          <form onSubmit={confirm} className="mt-6 flex gap-3 items-end flex-wrap">
            <div className="flex-1 min-w-[180px]">
              <label className="overline text-[hsl(var(--ink-muted))] block mb-2">Код от приложението</label>
              <input type="text" inputMode="numeric" maxLength={6} required value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} className="w-full border border-[hsl(var(--line))] h-12 px-3 text-xl tracking-widest font-mono text-center" placeholder="000000" data-testid="twofa-confirm-code" />
            </div>
            <button type="submit" disabled={loading || code.length !== 6} className="btn btn-primary" data-testid="twofa-confirm-submit">
              {loading ? "Активиране…" : "Активирай"}
            </button>
            <button type="button" onClick={() => { setProvisioning(null); setCode(""); }} className="text-sm text-[hsl(var(--ink-muted))] hover:text-[hsl(var(--ink))]">Отказ</button>
          </form>
          {err && <p className="mt-3 text-sm text-[hsl(var(--danger))]" data-testid="twofa-error">{err}</p>}
        </div>
      )}

      {/* Disable form */}
      {showDisable && (
        <form onSubmit={disable} className="mt-6 rounded-card border border-[hsl(var(--danger))] bg-white p-5" data-testid="twofa-disable-form">
          <h3 className="font-semibold">Деактивирай 2FA</h3>
          <p className="text-sm mt-1 text-[hsl(var(--ink-muted))]">Въведете текущ код за потвърждение.</p>
          <div className="mt-4 flex gap-3 items-end flex-wrap">
            <div className="flex-1 min-w-[180px]">
              <input type="text" inputMode="numeric" maxLength={6} required value={disableCode} onChange={(e) => setDisableCode(e.target.value.replace(/\D/g, ""))} className="w-full border border-[hsl(var(--line))] h-12 px-3 text-xl tracking-widest font-mono text-center" placeholder="000000" data-testid="twofa-disable-code" />
            </div>
            <button type="submit" disabled={loading || disableCode.length !== 6} className="px-5 py-2.5 rounded-card bg-[hsl(var(--danger))] text-white text-sm" data-testid="twofa-disable-submit">
              {loading ? "…" : "Деактивирай"}
            </button>
            <button type="button" onClick={() => { setShowDisable(false); setDisableCode(""); }} className="text-sm text-[hsl(var(--ink-muted))]">Отказ</button>
          </div>
          {err && <p className="mt-3 text-sm text-[hsl(var(--danger))]">{err}</p>}
        </form>
      )}

      {!provisioning && !backupCodes && !showDisable && (
        <div className="mt-6">
          {enabled ? (
            <button onClick={() => { setShowDisable(true); setErr(""); }} className="px-5 py-2.5 rounded-card border border-[hsl(var(--danger))] text-[hsl(var(--danger))] text-sm hover:bg-[hsl(var(--danger))] hover:text-white transition-colors" data-testid="twofa-disable-btn">
              Деактивирай 2FA
            </button>
          ) : (
            <button onClick={start} disabled={loading} className="btn btn-primary" data-testid="twofa-enable-btn">
              {loading ? "Зареждане…" : "Активирай 2FA"}
            </button>
          )}
          {err && <p className="mt-3 text-sm text-[hsl(var(--danger))]">{err}</p>}
        </div>
      )}
    </section>
  );
}
