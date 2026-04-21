import React, { useEffect, useState } from "react";
import { api } from "../lib/apiClient";
import { formatError } from "../lib/auth";
import { refreshSettings } from "../lib/settings";

// Each CMS content field now has BG/RO/EN variants.  The legacy non-suffixed
// field (e.g. `faq_content`) is kept for backwards compatibility and is used
// as fallback when `faq_content_<lang>` is empty.
const CONTENT_BASES = [
  { key: "how_it_works_content", label: "Как работи", placeholder: "Markdown съдържание за страница „Как работи“" },
  { key: "faq_content",          label: "FAQ — Често задавани въпроси", placeholder: "## Раздел\n\n**Въпрос?**\n\nОтговор…" },
  { key: "fees_content",         label: "Такси и комисионни", placeholder: "Markdown описание на таксите" },
  { key: "terms_content",        label: "Общи условия", placeholder: "Markdown текст на общите условия" },
  { key: "contacts_content",     label: "Контакти", placeholder: "Имейл, телефон, адрес и работно време" },
];
const CMS_LANGS = [
  { code: "bg", flag: "🇧🇬", label: "Български" },
  { code: "ro", flag: "🇷🇴", label: "Română" },
  { code: "en", flag: "🇬🇧", label: "English" },
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
        seo_title_bg: data.seo_title_bg ?? "",
        seo_title_ro: data.seo_title_ro ?? "",
        seo_title_en: data.seo_title_en ?? "",
        seo_description_bg: data.seo_description_bg ?? "",
        seo_description_ro: data.seo_description_ro ?? "",
        seo_description_en: data.seo_description_en ?? "",
        google_site_verification: data.google_site_verification ?? "",
        bing_site_verification: data.bing_site_verification ?? "",
        google_analytics_id: data.google_analytics_id ?? "",
        faq_content: data.faq_content ?? "",
        terms_content: data.terms_content ?? "",
        contacts_content: data.contacts_content ?? "",
        fees_content: data.fees_content ?? "",
        how_it_works_content: data.how_it_works_content ?? "",
        // Multi-language CMS variants (Phase 7)
        ...Object.fromEntries(
          CONTENT_BASES.flatMap((f) =>
            CMS_LANGS.map(({ code }) => [`${f.key}_${code}`, data[`${f.key}_${code}`] ?? ""])
          )
        ),
        og_image_url: data.og_image_url ?? "",
        maintenance_mode: !!data.maintenance_mode,
        maintenance_message: data.maintenance_message ?? "",
        hero_headline_bg: data.hero_headline_bg ?? "",
        hero_subtitle_bg: data.hero_subtitle_bg ?? "",
        hero_headline_ro: data.hero_headline_ro ?? "",
        hero_subtitle_ro: data.hero_subtitle_ro ?? "",
        hero_headline_en: data.hero_headline_en ?? "",
        hero_subtitle_en: data.hero_subtitle_en ?? "",
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
        seo_title_bg: form.seo_title_bg,
        seo_title_ro: form.seo_title_ro,
        seo_title_en: form.seo_title_en,
        seo_description_bg: form.seo_description_bg,
        seo_description_ro: form.seo_description_ro,
        seo_description_en: form.seo_description_en,
        google_site_verification: form.google_site_verification,
        bing_site_verification: form.bing_site_verification,
        google_analytics_id: form.google_analytics_id,
        faq_content: form.faq_content,
        terms_content: form.terms_content,
        contacts_content: form.contacts_content,
        fees_content: form.fees_content,
        how_it_works_content: form.how_it_works_content,
        ...Object.fromEntries(
          CONTENT_BASES.flatMap((f) =>
            CMS_LANGS.map(({ code }) => [`${f.key}_${code}`, form[`${f.key}_${code}`] ?? ""])
          )
        ),
        og_image_url: form.og_image_url,
        maintenance_mode: !!form.maintenance_mode,
        maintenance_message: form.maintenance_message,
        hero_headline_bg: form.hero_headline_bg,
        hero_subtitle_bg: form.hero_subtitle_bg,
        hero_headline_ro: form.hero_headline_ro,
        hero_subtitle_ro: form.hero_subtitle_ro,
        hero_headline_en: form.hero_headline_en,
        hero_subtitle_en: form.hero_subtitle_en,
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

      {/* SEO — multi-language */}
      <section className="rounded-card border border-[hsl(var(--line))] bg-white p-6">
        <h2 className="font-serif text-2xl">SEO на заглавна страница</h2>
        <p className="mt-2 text-sm text-[hsl(var(--ink-muted))]">
          Показват се в Google и при споделяне. Попълнете за всеки език — ако полето е празно за RO/EN, ще се използва българската версия като fallback.
        </p>
        <div className="mt-5 space-y-8">
          {CMS_LANGS.map(({ code, flag, label }) => (
            <div key={code} className="rounded-card border border-[hsl(var(--line))] p-4 bg-[hsl(var(--surface))]" data-testid={`seo-lang-${code}`}>
              <div className="flex items-center gap-2 mb-3">
                <span className="text-xl" aria-hidden>{flag}</span>
                <span className="overline text-[hsl(var(--ink))]">{label}</span>
              </div>
              <Field label="Заглавие (title)" testid={`seo-title-${code}`}>
                <input type="text" value={form[`seo_title_${code}`]}
                  onChange={(e) => set(`seo_title_${code}`, e.target.value)}
                  maxLength={120}
                  className="w-full border border-[hsl(var(--line))] h-11 px-3 text-sm bg-white"
                  data-testid={`seo-title-input-${code}`}
                />
              </Field>
              <Field label="Описание (description)" testid={`seo-desc-${code}`}>
                <textarea rows={3} value={form[`seo_description_${code}`]}
                  onChange={(e) => set(`seo_description_${code}`, e.target.value)}
                  maxLength={320}
                  className="w-full border border-[hsl(var(--line))] p-3 text-sm bg-white"
                  data-testid={`seo-desc-input-${code}`}
                />
              </Field>
            </div>
          ))}
          <Field label="Социална картинка (OG image URL)" testid="seo-og-image" span={2}>
            <input
              type="url"
              value={form.og_image_url}
              onChange={(e) => set("og_image_url", e.target.value)}
              placeholder="https://autobids.bg/brand/og.jpg"
              className="w-full border border-[hsl(var(--line))] h-11 px-3 text-sm font-mono"
              data-testid="seo-og-image-input"
            />
            {form.og_image_url && (
              <div className="mt-3 aspect-[1200/630] w-full max-w-md overflow-hidden rounded-card border border-[hsl(var(--line))] bg-[hsl(var(--surface))]">
                <img src={form.og_image_url} alt="OG preview" className="w-full h-full object-cover" />
              </div>
            )}
            <p className="mt-2 text-xs text-[hsl(var(--ink-muted))]">Статична картинка за социално споделяне на началната страница. Обявите автоматично ползват снимка на автомобила.</p>
          </Field>
        </div>
      </section>

      {/* Maintenance mode */}
      <section className="rounded-card border border-amber-300 bg-amber-50 p-6" data-testid="maintenance-section">
        <h2 className="font-serif text-2xl text-amber-900">Режим на поддръжка</h2>
        <p className="mt-2 text-sm text-amber-800">Когато е включен, сайтът продължава да се вижда, но записите (подаване, наддаване, коментари) се блокират с 503.</p>
        <div className="mt-5 space-y-4">
          <label className="flex items-center gap-3 cursor-pointer">
            <input type="checkbox" checked={!!form.maintenance_mode} onChange={(e) => set("maintenance_mode", e.target.checked)} className="h-4 w-4" data-testid="maintenance-toggle" />
            <span className="text-sm font-medium">Активирай режим на поддръжка</span>
          </label>
          <Field label="Съобщение към посетителите" testid="maintenance-message">
            <textarea
              rows={2}
              value={form.maintenance_message}
              onChange={(e) => set("maintenance_message", e.target.value)}
              maxLength={400}
              className="w-full border border-amber-300 p-3 text-sm bg-white"
              data-testid="maintenance-message-input"
            />
          </Field>
        </div>
      </section>

      {/* Hero headline CMS — multi-language */}
      <section className="rounded-card border border-[hsl(var(--line))] bg-white p-6" data-testid="hero-cms-section">
        <h2 className="font-serif text-2xl">Hero текст на началната страница</h2>
        <p className="mt-2 text-sm text-[hsl(var(--ink-muted))] max-w-3xl">
          Редактирайте заглавието и подзаглавието на hero секцията на началната страница, отделно за всеки език. Оставете празно, за да се използва версията по подразбиране от преводите. Използвайте нов ред за пренасяне. Заглавието е в режим rich text — за курсив поставете <code className="text-xs font-mono">&lt;em&gt;…&lt;/em&gt;</code>.
        </p>
        <div className="mt-5 space-y-8">
          {[
            { code: "bg", flag: "🇧🇬", label: "Български" },
            { code: "ro", flag: "🇷🇴", label: "Română" },
            { code: "en", flag: "🇬🇧", label: "English" },
          ].map(({ code, flag, label }) => (
            <div key={code} className="rounded-card border border-[hsl(var(--line))] p-4 bg-[hsl(var(--surface))]" data-testid={`hero-lang-${code}`}>
              <div className="flex items-center gap-2 mb-3">
                <span className="text-xl" aria-hidden>{flag}</span>
                <span className="overline text-[hsl(var(--ink))]">{label}</span>
              </div>
              <Field label="Заглавие (hero headline)" testid={`hero-headline-${code}`}>
                <textarea
                  rows={2}
                  value={form[`hero_headline_${code}`]}
                  onChange={(e) => set(`hero_headline_${code}`, e.target.value)}
                  placeholder={code === "bg"
                    ? "Открийте <em>изключителни</em>\nавтомобили."
                    : code === "ro"
                    ? "Descoperă <em>mașini</em>\nexcepționale."
                    : "Discover <em>exceptional</em>\ncars."}
                  maxLength={200}
                  className="w-full border border-[hsl(var(--line))] p-3 text-sm bg-white"
                  data-testid={`hero-headline-input-${code}`}
                />
              </Field>
              <Field label="Подзаглавие (subtitle)" testid={`hero-subtitle-${code}`}>
                <textarea
                  rows={3}
                  value={form[`hero_subtitle_${code}`]}
                  onChange={(e) => set(`hero_subtitle_${code}`, e.target.value)}
                  maxLength={400}
                  className="w-full border border-[hsl(var(--line))] p-3 text-sm bg-white"
                  data-testid={`hero-subtitle-input-${code}`}
                />
              </Field>
            </div>
          ))}
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

      {/* Content pages — multi-language CMS (Phase 7) */}
      {CONTENT_BASES.map((f) => (
        <CmsMultiLangField key={f.key} field={f} form={form} set={set} />
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

function CmsMultiLangField({ field, form, set }) {
  const [active, setActive] = useState("bg");
  if (!form) return null;
  return (
    <section className="rounded-card border border-[hsl(var(--line))] bg-white p-6" data-testid={`cms-${field.key}`}>
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h2 className="font-serif text-2xl">{field.label}</h2>
          <p className="mt-2 text-xs text-[hsl(var(--ink-muted))]">
            Markdown се поддържа. Поддържат се три езика — BG/RO/EN. Ако дадена езикова версия е празна, автоматично се показва BG версията.
          </p>
        </div>
        <div className="inline-flex rounded-card border border-[hsl(var(--line))] overflow-hidden" data-testid={`cms-tabs-${field.key}`}>
          {CMS_LANGS.map(({ code, flag, label }, i) => (
            <button
              key={code}
              type="button"
              onClick={() => setActive(code)}
              className={`px-3 py-1.5 text-xs flex items-center gap-1.5 ${i > 0 ? "border-l border-[hsl(var(--line))]" : ""} ${active === code ? "bg-[hsl(var(--ink))] text-white" : "bg-white hover:bg-[hsl(var(--surface))]"}`}
              data-testid={`cms-tab-${field.key}-${code}`}
            >
              <span aria-hidden>{flag}</span> {label}
            </button>
          ))}
        </div>
      </div>
      {CMS_LANGS.map(({ code }) => {
        const key = `${field.key}_${code}`;
        return (
          <textarea
            key={key}
            rows={12}
            value={form[key] ?? ""}
            placeholder={field.placeholder}
            onChange={(e) => set(key, e.target.value)}
            className={`mt-3 w-full border border-[hsl(var(--line))] p-3 text-sm font-mono ${active === code ? "" : "hidden"}`}
            data-testid={`content-${key}`}
          />
        );
      })}
    </section>
  );
}
