import React, { useEffect, useState } from "react";
import { api } from "../lib/apiClient";
import { formatError } from "../lib/auth";
import { refreshSettings } from "../lib/settings";
import { getDefaultCmsHtml } from "../lib/cmsDefaults";

// Each CMS content field now has BG/RO/EN variants.  The legacy non-suffixed
// field (e.g. `faq_content`) is kept for backwards compatibility and is used
// as fallback when `faq_content_<lang>` is empty.
//
// Всеки CMS блок има два режима:
//   1. Markdown (`<base>_<lang>`) — текущото поведение
//   2. Direct HTML (`<base_short>_html_<lang>`) — нов режим за директно
//      пишещ admin (примерно: <h2>, <a href>, <table>, <img>...).
// Ако HTML версията е попълнена → има приоритет при render.
const CONTENT_BASES = [
  { key: "how_it_works_content", htmlBase: "how_it_works", label: "Как работи" },
  { key: "faq_content",          htmlBase: "faq",          label: "FAQ — Често задавани въпроси" },
  { key: "fees_content",         htmlBase: "fees",         label: "Такси и комисионни" },
  { key: "terms_content",        htmlBase: "terms",        label: "Общи условия" },
  { key: "contacts_content",     htmlBase: "contacts",     label: "Контакти" },
];
const CMS_LANGS = [
  { code: "bg", flag: "🇧🇬", label: "Български" },
  { code: "ro", flag: "🇷🇴", label: "Română" },
  { code: "en", flag: "🇬🇧", label: "English" },
];

export default function AdminSettingsTab() {
  const [form, setForm] = useState(null);
  // Запомняме default HTML стойностите при load — на save изпращаме само
  // полета, които админът РЕАЛНО е променил (иначе бихме персистирали
  // целия default за всички 5 страници при първо запазване).
  const [initialHtmlDefaults, setInitialHtmlDefaults] = useState({});
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  useEffect(() => { load(); }, []);

  const load = async () => {
    try {
      const { data } = await api.get("/admin/settings");
      // Prefill default HTML за всеки празен `<base>_html_<lang>` →
      // позволява на админа да вижда и редактира текущото съдържание като
      // starting point.  НЕ се записва в DB докато не натисне "Запази".
      const ctx = {
        pct: data.buyer_fee_pct ?? 2,
        min: data.buyer_fee_min_eur ?? 150,
        max: data.buyer_fee_max_eur ?? 4000,
        brand: "Auto&Bid",
      };
      const htmlPrefill = Object.fromEntries(
        CONTENT_BASES.flatMap((f) =>
          CMS_LANGS.map(({ code }) => {
            const stored = (data[`${f.htmlBase}_html_${code}`] || "").trim();
            return [
              `${f.htmlBase}_html_${code}`,
              stored || getDefaultCmsHtml(f.htmlBase, code, ctx),
            ];
          })
        )
      );
      // Запазваме кои полета са били prefill-нати с default (не stored).
      // На Save ще пропуснем тези, които не са променяни.
      const defaultsMap = Object.fromEntries(
        CONTENT_BASES.flatMap((f) =>
          CMS_LANGS.map(({ code }) => {
            const stored = (data[`${f.htmlBase}_html_${code}`] || "").trim();
            const def = getDefaultCmsHtml(f.htmlBase, code, ctx);
            return [`${f.htmlBase}_html_${code}`, stored ? null : def];
          })
        )
      );
      setInitialHtmlDefaults(defaultsMap);
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
        // Multi-language CMS variants (Phase 7) — Markdown
        ...Object.fromEntries(
          CONTENT_BASES.flatMap((f) =>
            CMS_LANGS.map(({ code }) => [`${f.key}_${code}`, data[`${f.key}_${code}`] ?? ""])
          )
        ),
        // Direct-HTML CMS варианти (нов режим) — prefill с default ако е празно
        ...htmlPrefill,
        og_image_url: data.og_image_url ?? "",
        favicon_url: data.favicon_url ?? "",
        maintenance_mode: !!data.maintenance_mode,
        maintenance_message: data.maintenance_message ?? "",
        deindex_mode: !!data.deindex_mode,
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
        // Markdown CMS полетата вече не се редактират през UI, но запазваме
        // съществуващите стойности при save (за да не ги изтрием неволно).
        // Direct-HTML payload — пропускаме полета, които все още равняват
        // default-а (не са пипнати от админа), за да не персистираме defaults.
        ...Object.fromEntries(
          CONTENT_BASES.flatMap((f) =>
            CMS_LANGS.map(({ code }) => {
              const key = `${f.htmlBase}_html_${code}`;
              const cur = form[key] ?? "";
              const def = initialHtmlDefaults[key];
              if (def != null && cur === def) {
                // Незасегнат default — НЕ изпращаме (запазваме stored като "").
                return [key, undefined];
              }
              return [key, cur];
            }).filter(([, v]) => v !== undefined)
          )
        ),
        og_image_url: form.og_image_url,
        favicon_url: form.favicon_url,
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
              placeholder="https://auto-bid.bg/brand/og.jpg"
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

          <Field label="Favicon (URL към .ico / .png — иконката в таба)" testid="seo-favicon" span={2}>
            <input
              type="url"
              value={form.favicon_url}
              onChange={(e) => set("favicon_url", e.target.value)}
              placeholder="https://autoandbid.com/favicon.ico"
              className="w-full border border-[hsl(var(--line))] h-11 px-3 text-sm font-mono"
              data-testid="favicon-url-input"
            />
            {form.favicon_url && (
              <div className="mt-3 inline-flex items-center gap-3 px-3 py-2 rounded-card border border-[hsl(var(--line))] bg-[hsl(var(--surface))]">
                <img src={form.favicon_url} alt="favicon preview" className="w-8 h-8 object-contain" />
                <span className="text-xs text-[hsl(var(--ink-muted))] font-mono break-all">{form.favicon_url}</span>
              </div>
            )}
            <p className="mt-2 text-xs text-[hsl(var(--ink-muted))]">Препоръчителни размери: 32×32, 48×48 или 64×64. Поддържа .ico, .png и .svg. Промяната се прилага веднага в браузъра.</p>
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

      {/* Deindex mode — pre-launch SEO gate. NOT a login gate: тестерите виждат
          нормалния сайт, просто search engines получават noindex/nofollow.*/}
      <section className="rounded-card border border-rose-300 bg-rose-50 p-6" data-testid="deindex-section">
        <h2 className="font-serif text-2xl text-rose-900">Deindex режим (пре-лансиране)</h2>
        <p className="mt-2 text-sm text-rose-900/90">
          Скрива сайта от Google / Bing / Yandex преди официалния launch. Когато е активен:
        </p>
        <ul className="mt-2 list-disc pl-5 text-sm text-rose-900/90 space-y-1">
          <li><code className="text-xs font-mono bg-white px-1 rounded">/robots.txt</code> връща <code className="text-xs font-mono bg-white px-1 rounded">Disallow: /</code></li>
          <li>Всеки API отговор носи header <code className="text-xs font-mono bg-white px-1 rounded">X-Robots-Tag: noindex, nofollow, noarchive, nosnippet</code></li>
          <li>Фронтенд добавя <code className="text-xs font-mono bg-white px-1 rounded">&lt;meta name="robots" content="noindex,nofollow,noarchive,nosnippet"&gt;</code> към <code className="text-xs font-mono bg-white px-1 rounded">&lt;head&gt;</code></li>
          <li><code className="text-xs font-mono bg-white px-1 rounded">/sitemap.xml</code> и <code className="text-xs font-mono bg-white px-1 rounded">/sitemap-images.xml</code> връщат 404</li>
        </ul>
        <p className="mt-3 text-xs text-rose-900/80">
          ⚠️ НЕ блокира логин, API или админ панела. Всички тестери продължават да използват сайта нормално. Изключете преди launch.
        </p>
        <div className="mt-5">
          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={!!form.deindex_mode}
              onChange={(e) => set("deindex_mode", e.target.checked)}
              className="h-4 w-4"
              data-testid="deindex-toggle"
            />
            <span className="text-sm font-medium">Активирай deindex режим</span>
            {form.deindex_mode && (
              <span className="ml-2 text-[10px] font-bold uppercase tracking-wider bg-rose-600 text-white px-2 py-0.5 rounded-full" data-testid="deindex-active-badge">
                Активен
              </span>
            )}
          </label>
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
            Директен HTML редактор. Скриптове и event handler-и се премахват автоматично при render. Поддържат се: h1-h6, p, a, img, table, ul/ol, blockquote, code и др. Оставете полето напълно празно, за да върнете стандартното съдържание на страницата.
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
        const htmlKey = `${field.htmlBase}_html_${code}`;
        return (
          <textarea
            key={htmlKey}
            rows={16}
            value={form[htmlKey] ?? ""}
            placeholder={`<h2>Заглавие</h2>\n<p>Въведете текст с <strong>HTML</strong> форматиране…</p>\n<ul>\n  <li>точка</li>\n</ul>`}
            onChange={(e) => set(htmlKey, e.target.value)}
            className={`mt-3 w-full border border-[hsl(var(--line))] p-3 text-sm font-mono ${active === code ? "" : "hidden"}`}
            data-testid={`content-${htmlKey}`}
            spellCheck={false}
          />
        );
      })}
    </section>
  );
}
