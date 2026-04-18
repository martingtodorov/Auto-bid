import React, { useEffect, useState } from "react";
import { api } from "../lib/apiClient";
import { formatError } from "../lib/auth";
import { refreshSettings } from "../lib/settings";

const CONTENT_FIELDS = [
  { key: "how_it_works_content", label: "Как работи", placeholder: "Markdown съдържание за страница „Как работи“" },
  { key: "faq_content", label: "FAQ — Често задавани въпроси", placeholder: "## Раздел\n\n**Въпрос?**\n\nОтговор…" },
  { key: "fees_content", label: "Такси и комисионни", placeholder: "Markdown описание на таксите" },
  { key: "terms_content", label: "Общи условия", placeholder: "Markdown текст на общите условия" },
  { key: "contacts_content", label: "Контакти", placeholder: "Имейл, телефон, адрес и работно време" },
];

export default function AdminSettingsTab() {
  const [form, setForm] = useState(null);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  useEffect(() => { load(); }, []);

  const load = async () => {
    try {
      const { data } = await api.get("/admin/settings");
      setForm({
        buyer_fee_pct: data.buyer_fee_pct ?? 2.0,
        buyer_fee_min_eur: data.buyer_fee_min_eur ?? 150,
        buyer_fee_max_eur: data.buyer_fee_max_eur ?? 4000,
        seo_title: data.seo_title ?? "",
        seo_description: data.seo_description ?? "",
        google_site_verification: data.google_site_verification ?? "",
        bing_site_verification: data.bing_site_verification ?? "",
        google_analytics_id: data.google_analytics_id ?? "",
        faq_content: data.faq_content ?? "",
        terms_content: data.terms_content ?? "",
        contacts_content: data.contacts_content ?? "",
        fees_content: data.fees_content ?? "",
        how_it_works_content: data.how_it_works_content ?? "",
      });
    } catch (e) { setErr(formatError(e)); }
  };

  const save = async () => {
    setErr(""); setMsg(""); setSaving(true);
    try {
      const payload = {
        buyer_fee_pct: Number(form.buyer_fee_pct),
        buyer_fee_min_eur: Number(form.buyer_fee_min_eur),
        buyer_fee_max_eur: Number(form.buyer_fee_max_eur),
        seo_title: form.seo_title,
        seo_description: form.seo_description,
        google_site_verification: form.google_site_verification,
        bing_site_verification: form.bing_site_verification,
        google_analytics_id: form.google_analytics_id,
        faq_content: form.faq_content,
        terms_content: form.terms_content,
        contacts_content: form.contacts_content,
        fees_content: form.fees_content,
        how_it_works_content: form.how_it_works_content,
      };
      await api.put("/admin/settings", payload);
      await refreshSettings();
      setMsg("Запазено");
      setTimeout(() => setMsg(""), 2500);
    } catch (e) { setErr(formatError(e)); }
    finally { setSaving(false); }
  };

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  if (!form) return <div className="mt-10 text-[hsl(var(--ink-muted))]">Зареждане…</div>;

  return (
    <div className="mt-10 space-y-10" data-testid="admin-settings-tab">
      {/* Fees */}
      <section className="rounded-card border border-[hsl(var(--line))] bg-white p-6">
        <h2 className="font-serif text-2xl">Такса за купувач и pre-authorization</h2>
        <p className="mt-2 text-sm text-[hsl(var(--ink-muted))] max-w-2xl">
          Това е процентът, който се използва и като buyer's premium, и като pre-authorization върху картата на наддавача. При промяна стойността се прилага моментално за всички нови наддавания.
        </p>
        <div className="mt-5 grid grid-cols-1 md:grid-cols-3 gap-4">
          <Field label="Такса купувач (%)" testid="buyer-fee-pct">
            <input type="number" step="0.1" min="0" max="25" value={form.buyer_fee_pct}
              onChange={(e) => set("buyer_fee_pct", e.target.value)}
              className="w-full border border-[hsl(var(--line))] h-11 px-3 text-sm" />
          </Field>
          <Field label="Минимална такса (EUR)" testid="buyer-fee-min">
            <input type="number" step="1" min="0" value={form.buyer_fee_min_eur}
              onChange={(e) => set("buyer_fee_min_eur", e.target.value)}
              className="w-full border border-[hsl(var(--line))] h-11 px-3 text-sm" />
          </Field>
          <Field label="Максимална такса (EUR)" testid="buyer-fee-max">
            <input type="number" step="1" min="0" value={form.buyer_fee_max_eur}
              onChange={(e) => set("buyer_fee_max_eur", e.target.value)}
              className="w-full border border-[hsl(var(--line))] h-11 px-3 text-sm" />
          </Field>
        </div>
      </section>

      {/* SEO */}
      <section className="rounded-card border border-[hsl(var(--line))] bg-white p-6">
        <h2 className="font-serif text-2xl">SEO на заглавна страница</h2>
        <p className="mt-2 text-sm text-[hsl(var(--ink-muted))]">Показват се в Google и при споделяне.</p>
        <div className="mt-5 space-y-4">
          <Field label="Заглавие (title)" testid="seo-title">
            <input type="text" value={form.seo_title}
              onChange={(e) => set("seo_title", e.target.value)}
              maxLength={120}
              className="w-full border border-[hsl(var(--line))] h-11 px-3 text-sm" />
          </Field>
          <Field label="Описание (description)" testid="seo-desc">
            <textarea rows={3} value={form.seo_description}
              onChange={(e) => set("seo_description", e.target.value)}
              maxLength={320}
              className="w-full border border-[hsl(var(--line))] p-3 text-sm" />
          </Field>
        </div>
      </section>

      {/* Search Engine Verification */}
      <section className="rounded-card border border-[hsl(var(--line))] bg-white p-6">
        <h2 className="font-serif text-2xl">Потвърждение на собственост (Search Console)</h2>
        <p className="mt-2 text-sm text-[hsl(var(--ink-muted))]">
          Поставете само съдържанието на meta тага (не целия HTML). Пример за Google: „<code className="text-xs font-mono">abcdef1234567890</code>" от <code className="text-xs">&lt;meta name="google-site-verification" content="..."&gt;</code>.
        </p>
        <div className="mt-5 space-y-4">
          <Field label="Google Search Console — google-site-verification" testid="gsc-verification">
            <input
              type="text"
              value={form.google_site_verification}
              onChange={(e) => set("google_site_verification", e.target.value.trim())}
              placeholder="Напр. oZ7q8Xj...Kf9aA"
              maxLength={200}
              className="w-full border border-[hsl(var(--line))] h-11 px-3 text-sm font-mono"
            />
          </Field>
          <Field label="Bing Webmaster Tools — msvalidate.01" testid="bing-verification">
            <input
              type="text"
              value={form.bing_site_verification}
              onChange={(e) => set("bing_site_verification", e.target.value.trim())}
              placeholder="Напр. 1A2B3C4D5E6F7G8H9I0J"
              maxLength={200}
              className="w-full border border-[hsl(var(--line))] h-11 px-3 text-sm font-mono"
            />
          </Field>
          <Field label="Google Analytics 4 Measurement ID" testid="ga-id">
            <input
              type="text"
              value={form.google_analytics_id}
              onChange={(e) => set("google_analytics_id", e.target.value.trim())}
              placeholder="G-XXXXXXXXXX"
              pattern="^G-[A-Z0-9]{4,}$"
              maxLength={50}
              className="w-full border border-[hsl(var(--line))] h-11 px-3 text-sm font-mono"
            />
            <p className="mt-1 text-xs text-[hsl(var(--ink-muted))]">Трябва да започва с „G-". Оставете празно, за да изключите трекинга.</p>
          </Field>
        </div>
      </section>

      {/* Content pages */}
      {CONTENT_FIELDS.map((f) => (
        <section key={f.key} className="rounded-card border border-[hsl(var(--line))] bg-white p-6">
          <h2 className="font-serif text-2xl">{f.label}</h2>
          <p className="mt-2 text-xs text-[hsl(var(--ink-muted))]">Markdown се поддържа (**удебелено**, *курсив*, ## Заглавие, списъци, [линк](https://…)).</p>
          <textarea
            rows={12}
            value={form[f.key]}
            placeholder={f.placeholder}
            onChange={(e) => set(f.key, e.target.value)}
            className="mt-3 w-full border border-[hsl(var(--line))] p-3 text-sm font-mono"
            data-testid={`content-${f.key}`}
          />
        </section>
      ))}

      <div className="sticky bottom-4 flex justify-end gap-3 items-center">
        {msg && <span className="text-sm text-[hsl(var(--accent))]" data-testid="settings-save-ok">{msg}</span>}
        {err && <span className="text-sm text-[hsl(var(--danger))]" data-testid="settings-save-err">{err}</span>}
        <button
          onClick={save}
          disabled={saving}
          className="btn btn-accent !px-8 shadow-lg"
          data-testid="admin-settings-save"
        >
          {saving ? "Запазване…" : "Запази промените"}
        </button>
      </div>
    </div>
  );
}

function Field({ label, children, testid }) {
  return (
    <div data-testid={testid}>
      <label className="overline text-[hsl(var(--ink-muted))] block mb-1.5">{label}</label>
      {children}
    </div>
  );
}
