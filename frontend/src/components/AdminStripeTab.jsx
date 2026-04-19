import React, { useEffect, useState } from "react";
import { CreditCard, ShieldAlert, Check, Eye, EyeOff, Info } from "lucide-react";
import { api } from "../lib/apiClient";
import { formatError } from "../lib/auth";

export default function AdminStripeTab() {
  const [cfg, setCfg] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");

  // editable form
  const [form, setForm] = useState({
    mode: "test",
    stripe_enabled: false,
    stripe_publishable_key_test: "",
    stripe_publishable_key_live: "",
    stripe_secret_key_test: "",
    stripe_secret_key_live: "",
    stripe_webhook_secret_test: "",
    stripe_webhook_secret_live: "",
  });
  const [show, setShow] = useState({ st: false, sl: false, wt: false, wl: false });

  const load = async () => {
    setLoading(true); setErr("");
    try {
      const { data } = await api.get("/admin/stripe");
      setCfg(data);
      setForm((f) => ({
        ...f,
        mode: data.mode || "test",
        stripe_enabled: !!data.stripe_enabled,
        stripe_publishable_key_test: data.stripe_publishable_key_test || "",
        stripe_publishable_key_live: data.stripe_publishable_key_live || "",
      }));
    } catch (e) { setErr(formatError(e)); }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  const onSave = async (e) => {
    e.preventDefault();
    setMsg(""); setErr(""); setSaving(true);
    try {
      // Only send non-empty secret fields (empty = keep existing)
      const payload = {
        mode: form.mode,
        stripe_enabled: form.stripe_enabled,
        stripe_publishable_key_test: form.stripe_publishable_key_test || undefined,
        stripe_publishable_key_live: form.stripe_publishable_key_live || undefined,
        stripe_secret_key_test: form.stripe_secret_key_test || undefined,
        stripe_secret_key_live: form.stripe_secret_key_live || undefined,
        stripe_webhook_secret_test: form.stripe_webhook_secret_test || undefined,
        stripe_webhook_secret_live: form.stripe_webhook_secret_live || undefined,
      };
      await api.put("/admin/stripe", payload);
      // Clear secret inputs after save (we never re-display them)
      setForm((f) => ({
        ...f,
        stripe_secret_key_test: "",
        stripe_secret_key_live: "",
        stripe_webhook_secret_test: "",
        stripe_webhook_secret_live: "",
      }));
      setMsg("Записано успешно.");
      setTimeout(() => setMsg(""), 2500);
      await load();
    } catch (e) { setErr(formatError(e)); }
    finally { setSaving(false); }
  };

  if (loading) return <div className="mt-10 py-16 text-center text-sm text-[hsl(var(--ink-muted))]">Зареждане…</div>;

  return (
    <div className="mt-10 max-w-[900px]" data-testid="admin-stripe-tab">
      <div className="rounded-card border border-[hsl(var(--line))] bg-white p-6 lg:p-8">
        <div className="flex items-center gap-3">
          <CreditCard size={20} className="text-[hsl(var(--accent))]" />
          <h2 className="font-serif text-2xl">Stripe конфигурация</h2>
        </div>
        <p className="mt-3 text-sm text-[hsl(var(--ink-muted))]">
          Управлявайте Stripe ключовете за приеманe на buyer fee при наддаване. Секретните ключове се съхраняват само на сървъра — не се излъчват към frontend и никога не се връщат в четим вид след запис.
        </p>

        <div className="mt-4 rounded-card border border-amber-300 bg-amber-50 p-4 flex items-start gap-3">
          <Info size={16} className="mt-0.5 text-amber-700" />
          <div className="text-xs text-amber-900">
            <strong>Сигурност:</strong> Оставяйте секретно поле празно, ако не искате да го променяте — запазва се предишната стойност. Промените се записват в audit log.
          </div>
        </div>

        <form onSubmit={onSave} className="mt-6 space-y-6">
          {/* Mode + enabled */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            <div>
              <label className="overline text-[hsl(var(--ink-muted))] block mb-2">Режим</label>
              <div className="inline-flex rounded-card border border-[hsl(var(--line))] overflow-hidden bg-white" data-testid="stripe-mode-toggle">
                {["test", "live"].map((m, i) => (
                  <button
                    type="button"
                    key={m}
                    onClick={() => setForm((f) => ({ ...f, mode: m }))}
                    className={`px-6 py-2.5 text-sm font-medium ${i > 0 ? "border-l border-[hsl(var(--line))]" : ""} ${form.mode === m ? (m === "live" ? "bg-[hsl(var(--danger))] text-white" : "bg-[hsl(var(--ink))] text-white") : ""}`}
                    data-testid={`stripe-mode-${m}`}
                  >
                    {m === "test" ? "Тест" : "Live"}
                  </button>
                ))}
              </div>
            </div>
            <label className="flex items-center gap-2 cursor-pointer pt-8" data-testid="stripe-enabled-toggle">
              <input type="checkbox" checked={form.stripe_enabled} onChange={(e) => setForm((f) => ({ ...f, stripe_enabled: e.target.checked }))} className="h-4 w-4" />
              <span className="text-sm">Активирай Stripe плащанията</span>
            </label>
          </div>

          {/* Test keys */}
          <Group label="Тестови ключове">
            <Input
              label="Test publishable key (pk_test_…)"
              value={form.stripe_publishable_key_test}
              onChange={(v) => setForm((f) => ({ ...f, stripe_publishable_key_test: v }))}
              testid="stripe-pub-test"
              placeholder="pk_test_…"
            />
            <SecretInput
              label="Test secret key (sk_test_…)"
              current={cfg?.stripe_secret_key_test_masked}
              hasValue={cfg?.has_secret_test}
              value={form.stripe_secret_key_test}
              onChange={(v) => setForm((f) => ({ ...f, stripe_secret_key_test: v }))}
              show={show.st}
              onToggle={() => setShow((s) => ({ ...s, st: !s.st }))}
              testid="stripe-secret-test"
              placeholder="sk_test_…"
            />
            <SecretInput
              label="Test webhook secret (whsec_…)"
              current={cfg?.stripe_webhook_secret_test_masked}
              hasValue={cfg?.has_webhook_test}
              value={form.stripe_webhook_secret_test}
              onChange={(v) => setForm((f) => ({ ...f, stripe_webhook_secret_test: v }))}
              show={show.wt}
              onToggle={() => setShow((s) => ({ ...s, wt: !s.wt }))}
              testid="stripe-webhook-test"
              placeholder="whsec_…"
            />
          </Group>

          {/* Live keys */}
          <Group label="Live ключове" danger>
            <Input
              label="Live publishable key (pk_live_…)"
              value={form.stripe_publishable_key_live}
              onChange={(v) => setForm((f) => ({ ...f, stripe_publishable_key_live: v }))}
              testid="stripe-pub-live"
              placeholder="pk_live_…"
            />
            <SecretInput
              label="Live secret key (sk_live_…)"
              current={cfg?.stripe_secret_key_live_masked}
              hasValue={cfg?.has_secret_live}
              value={form.stripe_secret_key_live}
              onChange={(v) => setForm((f) => ({ ...f, stripe_secret_key_live: v }))}
              show={show.sl}
              onToggle={() => setShow((s) => ({ ...s, sl: !s.sl }))}
              testid="stripe-secret-live"
              placeholder="sk_live_…"
            />
            <SecretInput
              label="Live webhook secret (whsec_…)"
              current={cfg?.stripe_webhook_secret_live_masked}
              hasValue={cfg?.has_webhook_live}
              value={form.stripe_webhook_secret_live}
              onChange={(v) => setForm((f) => ({ ...f, stripe_webhook_secret_live: v }))}
              show={show.wl}
              onToggle={() => setShow((s) => ({ ...s, wl: !s.wl }))}
              testid="stripe-webhook-live"
              placeholder="whsec_…"
            />
          </Group>

          <div className="flex items-center gap-4 pt-3 border-t border-[hsl(var(--line))]">
            <button type="submit" disabled={saving} className="btn btn-primary" data-testid="stripe-save">
              {saving ? "Записване…" : "Запази настройките"}
            </button>
            {msg && <span className="text-sm text-[hsl(var(--accent))] inline-flex items-center gap-1.5"><Check size={14} />{msg}</span>}
            {err && <span className="text-sm text-[hsl(var(--danger))]" data-testid="stripe-error">{err}</span>}
          </div>
        </form>
      </div>

      <div className="mt-6 rounded-card border border-[hsl(var(--line))] bg-white p-5 text-sm">
        <div className="flex items-center gap-2">
          <ShieldAlert size={15} className="text-[hsl(var(--ink-muted))]" />
          <span className="font-semibold">Webhook URL за Stripe Dashboard</span>
        </div>
        <code className="mt-2 block text-xs bg-[hsl(var(--surface))] p-3 rounded-card border border-[hsl(var(--line))] break-all font-mono" data-testid="stripe-webhook-url">
          {window.location.origin}/api/webhooks/stripe
        </code>
        <p className="mt-2 text-xs text-[hsl(var(--ink-muted))]">Копирайте този адрес в Stripe Dashboard → Developers → Webhooks. Подписът се валидира с webhook secret-а на активния режим.</p>
      </div>
    </div>
  );
}

function Group({ label, danger, children }) {
  return (
    <div className={`rounded-card border ${danger ? "border-[hsl(var(--danger))]/40" : "border-[hsl(var(--line))]"} p-5 bg-[hsl(var(--surface))]`}>
      <div className={`overline mb-4 ${danger ? "text-[hsl(var(--danger))]" : "text-[hsl(var(--accent))]"}`}>{label}</div>
      <div className="space-y-4">{children}</div>
    </div>
  );
}

function Input({ label, value, onChange, placeholder, testid }) {
  return (
    <div>
      <label className="block text-xs text-[hsl(var(--ink-muted))] uppercase tracking-wider mb-1.5">{label}</label>
      <input type="text" value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} className="w-full border border-[hsl(var(--line))] h-11 px-3 text-sm font-mono bg-white" data-testid={testid} />
    </div>
  );
}

function SecretInput({ label, current, hasValue, value, onChange, placeholder, show, onToggle, testid }) {
  return (
    <div>
      <label className="flex items-center justify-between text-xs text-[hsl(var(--ink-muted))] uppercase tracking-wider mb-1.5">
        <span>{label}</span>
        {hasValue && <span className="normal-case text-xs text-[hsl(var(--accent))]">Запазена: {current}</span>}
      </label>
      <div className="flex gap-2">
        <input
          type={show ? "text" : "password"}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={hasValue ? "Оставете празно, за да запазите текущата" : placeholder}
          className="flex-1 border border-[hsl(var(--line))] h-11 px-3 text-sm font-mono bg-white"
          data-testid={testid}
          autoComplete="new-password"
        />
        <button type="button" onClick={onToggle} className="px-3 rounded-card border border-[hsl(var(--line))] bg-white hover:bg-[hsl(var(--surface))]" aria-label="toggle visibility">
          {show ? <EyeOff size={14} /> : <Eye size={14} />}
        </button>
      </div>
    </div>
  );
}
