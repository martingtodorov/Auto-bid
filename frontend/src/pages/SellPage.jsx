import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth, formatError } from "../lib/auth";
import { api } from "../lib/apiClient";
import { translateEnum } from "../lib/carTranslations";
import ImageUploader from "../components/ImageUploader";

const FUELS = ["Бензин", "Дизел", "Хибриден", "Електрически", "Газ/Бензин"];
const TRANSMISSIONS = ["Автоматична", "Ръчна"];
const BODY_TYPES = ["Седан", "Комби", "Хечбек", "Джип", "Купе", "Кабрио", "Ван", "Пикап"];
// Countries stored (and displayed) in English — sorted alphabetically with
// Bulgaria pinned on top as the default.
const COUNTRIES = [
  "Bulgaria",
  "Romania",
  "Albania",
  "Austria",
  "Belgium",
  "Bosnia and Herzegovina",
  "Croatia",
  "Cyprus",
  "Czech Republic",
  "Denmark",
  "Estonia",
  "Finland",
  "France",
  "Germany",
  "Greece",
  "Hungary",
  "Ireland",
  "Italy",
  "Kosovo",
  "Latvia",
  "Lithuania",
  "Luxembourg",
  "Malta",
  "Moldova",
  "Montenegro",
  "Netherlands",
  "North Macedonia",
  "Norway",
  "Poland",
  "Portugal",
  "Serbia",
  "Slovakia",
  "Slovenia",
  "Spain",
  "Sweden",
  "Switzerland",
  "Turkey",
  "Ukraine",
  "United Kingdom",
  "Other",
];

const inputCls = "w-full border border-[hsl(var(--line))] h-11 px-3 text-sm";

function Field({ label, children, span = 1 }) {
  return (
    <div className={`col-span-1 ${span === 2 ? "md:col-span-2" : ""}`}>
      <label className="overline text-[hsl(var(--ink-muted))] block mb-2">{label}</label>
      {children}
    </div>
  );
}

const emptyForm = (user) => ({
  title: "", make: "", model: "", year: 2020, mileage_km: 0,
  fuel: "Бензин", transmission: "Автоматична", body_type: "Седан",
  power_hp: 150, engine_cc: 2000, color: "",
  city: "София", country: "Bulgaria", description: "",
  vin: "",
  contact_email: user?.email || "",
  contact_phone: "",
  images_exterior: [],
  images_wheels: [],
  images_bumper: [],
  images_interior: [],
  starting_bid_eur: 5000, reserve_eur: "",
  no_reserve: false,
  buy_now_eur: "",
  vat_status: "exempt",         // "exempt" | "vat_inclusive"
  vat_rate_pct: 20,
  price_net_eur: "",
  price_gross_eur: "",
  duration_days: 10,
});

const IMG_CATEGORIES = [
  { id: "images_exterior", label: "Екстериор" },
  { id: "images_bumper",   label: "Предна броня" },
  { id: "images_wheels",   label: "Джанти" },
  { id: "images_interior", label: "Интериор" },
];

export default function SellPage() {
  const { t, i18n } = useTranslation();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState(() => emptyForm(user));
  const [err, setErr] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [loading, setLoading] = useState(false);

  // Prefill contact email once user loads
  useEffect(() => {
    if (user?.email) {
      setForm((p) => (p.contact_email ? p : { ...p, contact_email: user.email }));
    }
  }, [user]);

  // --- Move photo between categories / reorder ---
  const movePhoto = (fromCat, fromIdx, toCat, toIdx) => {
    if (!IMG_CATEGORIES.find((c) => c.id === fromCat)) return;
    if (!IMG_CATEGORIES.find((c) => c.id === toCat)) return;
    setForm((p) => {
      const fromList = [...(p[fromCat] || [])];
      const toList = fromCat === toCat ? fromList : [...(p[toCat] || [])];
      if (fromIdx < 0 || fromIdx >= fromList.length) return p;
      const [item] = fromList.splice(fromIdx, 1);
      if (fromCat === toCat) {
        const insertAt = toIdx == null ? fromList.length : Math.max(0, Math.min(toIdx, fromList.length));
        fromList.splice(insertAt, 0, item);
        return { ...p, [fromCat]: fromList };
      }
      const insertAt = toIdx == null ? toList.length : Math.max(0, Math.min(toIdx, toList.length));
      toList.splice(insertAt, 0, item);
      return { ...p, [fromCat]: fromList, [toCat]: toList };
    });
  };

  const set = (k, v) => setForm((p) => ({ ...p, [k]: v }));

  // Load dynamic makes list (admin CMS controlled; falls back gracefully)
  const [makes, setMakes] = useState([]);
  useEffect(() => {
    api.get("/makes").then((r) => setMakes(Array.isArray(r.data) ? r.data : [])).catch(() => setMakes([]));
  }, []);

  // Preview modal
  const [showPreview, setShowPreview] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (!user) return navigate("/login?next=/sell");
    setErr(""); setLoading(true);
    try {
      const ext = form.images_exterior || [];
      const wh = form.images_wheels || [];
      const bp = form.images_bumper || [];
      const intr = form.images_interior || [];
      if (!form.contact_email || !form.contact_phone) {
        setErr(t("sell.err_contacts"));
        setLoading(false);
        return;
      }
      const phoneDigits = (form.contact_phone || "").replace(/[^\d]/g, "");
      if (phoneDigits.length < 7) {
        setErr(t("sell.err_phone"));
        setLoading(false);
        return;
      }
      if (ext.length < 8 || wh.length < 4 || bp.length < 1 || intr.length < 4) {
        setErr(
          `Снимките не отговарят на минимума: екстериор ${ext.length}/8, джанти ${wh.length}/4, предна броня ${bp.length}/1, интериор ${intr.length}/4.`
        );
        setLoading(false);
        return;
      }
      // Цените се въвеждат като брутни (с ДДС) когато сделката е vat_inclusive.
      // Backend очаква нетни стойности → конвертираме gross → net = gross / (1 + rate/100).
      const isVatIncl = form.vat_status === "vat_inclusive";
      const vatRate = isVatIncl && form.vat_rate_pct ? Number(form.vat_rate_pct) : 0;
      const grossToNet = (gross) => {
        const g = Number(gross);
        if (!g) return g;
        if (!isVatIncl || !vatRate) return g;
        return Math.round((g / (1 + vatRate / 100)) * 100) / 100;
      };
      const payload = {
        ...form,
        images: [...ext, ...bp, ...wh, ...intr],
        images_exterior: ext,
        images_wheels: wh,
        images_bumper: bp,
        images_interior: intr,
        year: Number(form.year),
        mileage_km: Number(form.mileage_km),
        power_hp: Number(form.power_hp),
        engine_cc: Number(form.engine_cc),
        starting_bid_eur: grossToNet(form.starting_bid_eur),
        reserve_eur: (form.no_reserve || !form.reserve_eur) ? null : grossToNet(form.reserve_eur),
        no_reserve: !!form.no_reserve,
        buy_now_eur: form.buy_now_eur ? grossToNet(form.buy_now_eur) : null,
        vat_status: form.vat_status || "exempt",
        vat_rate_pct: isVatIncl && form.vat_rate_pct ? Number(form.vat_rate_pct) : null,
        price_net_eur: null,
        price_gross_eur: null,
        duration_days: Number(form.duration_days),
        contact_email: form.contact_email.trim(),
        contact_phone: form.contact_phone.trim(),
        vin: (form.vin || "").trim().toUpperCase(),
      };
      await api.post("/auctions", payload);
      setSubmitted(true);
    } catch (e) { setErr(formatError(e)); }
    finally { setLoading(false); }
  };

  const [importUrl, setImportUrl] = useState("");
  const [importing, setImporting] = useState(false);
  const [importMsg, setImportMsg] = useState("");
  const [importErr, setImportErr] = useState("");

  const importMobileBg = async () => {
    setImportErr(""); setImportMsg("");
    const url = (importUrl || "").trim();
    if (!url) { setImportErr("Поставете линк към обявата в mobile.bg"); return; }
    setImporting(true);
    try {
      const { data } = await api.post("/auctions/import-mobile-bg", { url });
      setForm((p) => ({
        ...p,
        title: data.title || p.title,
        make: data.make || p.make,
        model: data.model || p.model,
        year: data.year || p.year,
        mileage_km: data.mileage_km || p.mileage_km,
        fuel: data.fuel || p.fuel,
        transmission: data.transmission || p.transmission,
        body_type: data.body_type || p.body_type,
        power_hp: data.power_hp || p.power_hp,
        engine_cc: data.engine_cc || p.engine_cc,
        color: data.color || p.color,
        city: data.city || p.city,
        description: data.description || p.description,
        images_exterior: data.images && data.images.length ? data.images : p.images_exterior,
      }));
      const foundImgs = (data.images || []).length;
      setImportMsg(
        `Данните са заредени${foundImgs ? ` · ${foundImgs} снимки в "Екстериор"` : ""}. Проверете всички полета, задайте цена и доразпределете снимките по категории.`
      );
    } catch (e) { setImportErr(formatError(e)); }
    finally { setImporting(false); }
  };

  if (submitted) {
    return (
      <main className="py-24 text-center" data-testid="sell-success">
        <div className="max-w-lg mx-auto px-6">
          <div className="overline text-[hsl(var(--accent))]">{t("sell.success_overline")}</div>
          <h1 className="font-serif text-4xl mt-3">{t("sell.success_title")}</h1>
          <p className="mt-5 text-[hsl(var(--ink-muted))]">{t("sell.success_body")}</p>
          <button onClick={() => navigate("/")} className="btn btn-primary mt-8" data-testid="sell-success-home">{t("sell.success_home")}</button>
        </div>
      </main>
    );
  }

  return (
    <main data-testid="sell-page">
      <section className="rule-b">
        <div className="max-w-[1100px] mx-auto px-4 sm:px-6 lg:px-10 py-16">
          <div className="overline text-[hsl(var(--accent))]">{t("sell.overline")}</div>
          <div className="flex items-start justify-between gap-4 flex-wrap mt-3">
            <h1 className="font-serif text-4xl lg:text-5xl tracking-tight" data-testid="sell-hero-title">{t("sell.hero_title")}</h1>
          </div>
          <p className="mt-4 text-[hsl(var(--ink-muted))] max-w-2xl leading-relaxed">
            {t("sell.hero_subtitle")}
          </p>

          <div className="mt-10 rounded-card border border-[hsl(var(--accent))]/30 bg-[hsl(var(--accent-soft))] p-5" data-testid="mobile-bg-import">
            <div>
              <div className="overline text-[hsl(var(--accent))]">{t("sell.import_overline")}</div>
              <h3 className="font-serif text-xl mt-1.5">{t("sell.import_title")}</h3>
              <p className="text-sm text-[hsl(var(--ink))]/80 mt-1.5">
                {t("sell.import_description")}
              </p>
            </div>

            <div className="mt-4 flex flex-col sm:flex-row gap-2">
              <input
                type="url"
                value={importUrl}
                onChange={(e) => setImportUrl(e.target.value)}
                placeholder="https://www.mobile.bg/obiava-..."
                className="flex-1 border border-[hsl(var(--line))] h-11 px-3 text-sm bg-white"
                data-testid="import-url-input"
              />
              <button
                type="button"
                onClick={importMobileBg}
                disabled={importing}
                className="btn btn-accent !py-2 !px-5 shrink-0"
                data-testid="import-url-btn"
              >
                {importing ? t("sell.import_loading") : t("sell.import_cta")}
              </button>
            </div>
            {importMsg && <p className="mt-3 text-xs text-[hsl(var(--accent-ink))] font-semibold" data-testid="import-success">{importMsg}</p>}
            {importErr && <p className="mt-3 text-xs text-[hsl(var(--danger))]" data-testid="import-error">{importErr}</p>}
          </div>

          <form onSubmit={submit} className="mt-8 grid grid-cols-1 md:grid-cols-2 gap-5">
            <Field label={t("sell.form.title")} span={2}>
              <input required value={form.title} onChange={(e) => set("title", e.target.value)} className={inputCls} placeholder={t("sell.form.title_placeholder")} data-testid="sell-title" />
            </Field>
            <Field label={t("sell.form.make")}>
              <select required value={form.make} onChange={(e) => set("make", e.target.value)} className={inputCls} data-testid="sell-make">
                <option value="" disabled>{t("sell.form.pick_make")}</option>
                {makes.map((m) => <option key={m.id || m.name} value={m.name}>{m.name}</option>)}
              </select>
            </Field>
            <Field label={t("sell.form.model")}>
              <input required value={form.model} onChange={(e) => set("model", e.target.value)} className={inputCls} data-testid="sell-model" />
            </Field>
            <Field label={t("sell.form.year")}>
              <input type="number" required value={form.year} onChange={(e) => set("year", e.target.value)} className={inputCls} data-testid="sell-year" />
            </Field>
            <Field label={t("sell.form.mileage_km")}>
              <input type="number" required value={form.mileage_km} onChange={(e) => set("mileage_km", e.target.value)} className={inputCls} data-testid="sell-mileage" />
            </Field>
            <Field label={t("sell.form.fuel")}>
              <select value={form.fuel} onChange={(e) => set("fuel", e.target.value)} className={inputCls} data-testid="sell-fuel">
                {FUELS.map((o) => <option key={o} value={o}>{translateEnum(o, "fuel", i18n.language)}</option>)}
              </select>
            </Field>
            <Field label={t("sell.form.transmission")}>
              <select value={form.transmission} onChange={(e) => set("transmission", e.target.value)} className={inputCls} data-testid="sell-transmission">
                {TRANSMISSIONS.map((o) => <option key={o} value={o}>{translateEnum(o, "transmission", i18n.language)}</option>)}
              </select>
            </Field>
            <Field label={t("sell.form.body_type")}>
              <select value={form.body_type} onChange={(e) => set("body_type", e.target.value)} className={inputCls} data-testid="sell-body-type">
                {BODY_TYPES.map((o) => <option key={o} value={o}>{translateEnum(o, "body_type", i18n.language)}</option>)}
              </select>
            </Field>
            <Field label={t("sell.form.power_hp")}>
              <input type="number" value={form.power_hp} onChange={(e) => set("power_hp", e.target.value)} className={inputCls} />
            </Field>
            <Field label={t("sell.form.engine_cc")}>
              <input type="number" value={form.engine_cc} onChange={(e) => set("engine_cc", e.target.value)} className={inputCls} />
            </Field>
            <Field label={t("sell.form.colour")}>
              <input value={form.color} onChange={(e) => set("color", e.target.value)} className={inputCls} />
            </Field>
            <Field label={t("sell.form.city")}>
              <input value={form.city} onChange={(e) => set("city", e.target.value)} className={inputCls} data-testid="sell-city" />
            </Field>
            <Field label={t("sell.form.country")}>
              <select value={form.country} onChange={(e) => set("country", e.target.value)} className={inputCls} data-testid="sell-country">
                {COUNTRIES.map((o) => <option key={o} value={o}>{o}</option>)}
              </select>
            </Field>
            <Field label={t("sell.form.vat_status")} span={2}>
              <div className="rounded-card border border-[hsl(var(--line))] bg-[hsl(var(--surface))] p-4">
                <div className="flex gap-3 flex-wrap" data-testid="sell-vat-status">
                  {[{ v: "exempt", l: t("sell.form.vat_exempt") }, { v: "vat_inclusive", l: t("sell.form.vat_inclusive") }].map((o) => (
                    <label key={o.v} className={`flex items-center gap-2 px-4 py-2 rounded-card border cursor-pointer text-sm ${form.vat_status === o.v ? "border-[hsl(var(--accent))] bg-white" : "border-[hsl(var(--line))] bg-white"}`} data-testid={`sell-vat-${o.v}`}>
                      <input type="radio" name="vat_status" checked={form.vat_status === o.v} onChange={() => set("vat_status", o.v)} />
                      {o.l}
                    </label>
                  ))}
                </div>
                {form.vat_status === "vat_inclusive" && (
                  <div className="mt-4" data-testid="sell-vat-rate-block">
                    <label className="overline text-[hsl(var(--ink-muted))] block mb-1.5">{t("sell.form.vat_rate_pct", "ДДС %")}</label>
                    <div className="relative max-w-[200px]">
                      <input
                        type="number"
                        step="0.1"
                        min="0"
                        max="50"
                        required
                        value={form.vat_rate_pct}
                        onChange={(e) => set("vat_rate_pct", e.target.value)}
                        className={`${inputCls} pr-10`}
                        data-testid="sell-vat-rate"
                      />
                      <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[hsl(var(--ink-muted))] font-mono text-sm">%</span>
                    </div>
                    <p className="mt-1.5 text-xs text-[hsl(var(--ink-muted))]">{t("sell.form.vat_rate_hint", "Процент ДДС, който се добавя върху наддавката (напр. 20).")}</p>
                  </div>
                )}
              </div>
            </Field>
            <Field label={t("sell.form.starting_bid_eur")}>
              <input type="number" required value={form.starting_bid_eur} onChange={(e) => set("starting_bid_eur", e.target.value)} className={inputCls} data-testid="sell-starting-bid" />
              {form.vat_status === "vat_inclusive" && Number(form.starting_bid_eur) > 0 && Number(form.vat_rate_pct) > 0 && (
                <p className="mt-1.5 text-xs text-[hsl(var(--ink-muted))]" data-testid="sell-starting-bid-net">
                  {t("sell.form.without_vat_hint", {
                    rate: form.vat_rate_pct,
                    amount: (Number(form.starting_bid_eur) / (1 + Number(form.vat_rate_pct) / 100)).toLocaleString("bg-BG", { maximumFractionDigits: 2 }),
                  })}
                </p>
              )}
            </Field>
            <Field label={t("sell.form.reserve_eur")}>
              <input type="number" value={form.reserve_eur} disabled={form.no_reserve} onChange={(e) => set("reserve_eur", e.target.value)} className={`${inputCls} ${form.no_reserve ? "opacity-50" : ""}`} data-testid="sell-reserve" />
              {!form.no_reserve && form.vat_status === "vat_inclusive" && Number(form.reserve_eur) > 0 && Number(form.vat_rate_pct) > 0 && (
                <p className="mt-1.5 text-xs text-[hsl(var(--ink-muted))]" data-testid="sell-reserve-net">
                  {t("sell.form.without_vat_hint", {
                    rate: form.vat_rate_pct,
                    amount: (Number(form.reserve_eur) / (1 + Number(form.vat_rate_pct) / 100)).toLocaleString("bg-BG", { maximumFractionDigits: 2 }),
                  })}
                </p>
              )}
              <label className="mt-2 flex items-center gap-2 text-xs text-[hsl(var(--ink-muted))] cursor-pointer">
                <input type="checkbox" checked={!!form.no_reserve} onChange={(e) => set("no_reserve", e.target.checked)} data-testid="sell-no-reserve" />
                {t("sell.form.no_reserve_label")}
              </label>
            </Field>
            <Field label={t("sell.form.buy_now_eur")} span={2}>
              <input
                type="number"
                value={form.buy_now_eur}
                onChange={(e) => set("buy_now_eur", e.target.value)}
                className={inputCls}
                placeholder={t("sell.form.buy_now_placeholder", "Оставете празно, ако не желаете моментална покупка")}
                data-testid="sell-buy-now"
              />
              {form.buy_now_eur && Number(form.buy_now_eur) > 0 && form.vat_status === "vat_inclusive" && Number(form.vat_rate_pct) > 0 && (
                <p className="mt-1.5 text-xs text-[hsl(var(--ink-muted))]" data-testid="sell-buy-now-net">
                  {t("sell.form.without_vat_hint", {
                    rate: form.vat_rate_pct,
                    amount: (Number(form.buy_now_eur) / (1 + Number(form.vat_rate_pct) / 100)).toLocaleString("bg-BG", { maximumFractionDigits: 2 }),
                  })}
                </p>
              )}
              <p className="mt-1.5 text-xs text-[hsl(var(--ink-muted))]">{t("sell.form.buy_now_hint", "Купувачът може да приключи търга веднага на тази цена. Трябва да е поне колкото резерва и началната цена.")}</p>
            </Field>
            <Field label={t("sell.form.vin")} span={2}>
              <input
                value={form.vin}
                onChange={(e) => set("vin", e.target.value.toUpperCase())}
                className={inputCls}
                maxLength={17}
                minLength={11}
                required
                placeholder={t("sell.form.vin_placeholder")}
                data-testid="sell-vin"
              />
              <p className="mt-1.5 text-xs text-[hsl(var(--ink-muted))]">{t("sell.form.vin_required_hint", "VIN номерът е задължителен. Само латински букви и цифри (без I, O, Q), 11–17 знака.")}</p>
            </Field>
            <Field label="" span={2}>
              <div className="rounded-card border border-[hsl(var(--line))] bg-[hsl(var(--surface))] p-4">
                <div className="overline text-[hsl(var(--accent))] mb-1">{t("sell.form.contact_overline")}</div>
                <p className="text-xs text-[hsl(var(--ink-muted))] mb-3">{t("sell.form.contact_hint")}</p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="overline text-[hsl(var(--ink-muted))] block mb-1.5">{t("sell.form.contact_email")}</label>
                    <input type="email" required value={form.contact_email} onChange={(e) => set("contact_email", e.target.value)} className={inputCls} placeholder="name@example.com" data-testid="sell-contact-email" />
                  </div>
                  <div>
                    <label className="overline text-[hsl(var(--ink-muted))] block mb-1.5">{t("sell.form.contact_phone")}</label>
                    <input type="tel" required value={form.contact_phone} onChange={(e) => set("contact_phone", e.target.value)} className={inputCls} placeholder="+359 88 888 8888" data-testid="sell-contact-phone" />
                  </div>
                </div>
              </div>
            </Field>
            <Field label={t("sell.form.photos")} span={2}>
              <div className="space-y-3">
                <div className="text-xs text-[hsl(var(--ink-muted))] leading-relaxed">{t("sell.form.photos_hint")}</div>
                <ImageUploader
                  label={t("sell.form.exterior")}
                  helper={t("sell.form.exterior_helper")}
                  min={8}
                  max={20}
                  images={form.images_exterior}
                  onChange={(list) => set("images_exterior", list)}
                  testId="uploader-exterior"
                  category="images_exterior"
                  onMoveBetween={movePhoto}
                  availableCategories={IMG_CATEGORIES.filter((c) => c.id !== "images_exterior")}
                />
                <ImageUploader
                  label={t("sell.form.bumper")}
                  helper={t("sell.form.bumper_helper")}
                  min={1}
                  max={4}
                  images={form.images_bumper}
                  onChange={(list) => set("images_bumper", list)}
                  testId="uploader-bumper"
                  category="images_bumper"
                  onMoveBetween={movePhoto}
                  availableCategories={IMG_CATEGORIES.filter((c) => c.id !== "images_bumper")}
                />
                <ImageUploader
                  label={t("sell.form.wheels")}
                  helper={t("sell.form.wheels_helper")}
                  min={4}
                  max={8}
                  images={form.images_wheels}
                  onChange={(list) => set("images_wheels", list)}
                  testId="uploader-wheels"
                  category="images_wheels"
                  onMoveBetween={movePhoto}
                  availableCategories={IMG_CATEGORIES.filter((c) => c.id !== "images_wheels")}
                />
                <ImageUploader
                  label={t("sell.form.interior")}
                  helper={t("sell.form.interior_helper")}
                  min={4}
                  max={12}
                  images={form.images_interior}
                  onChange={(list) => set("images_interior", list)}
                  testId="uploader-interior"
                  category="images_interior"
                  onMoveBetween={movePhoto}
                  availableCategories={IMG_CATEGORIES.filter((c) => c.id !== "images_interior")}
                />
              </div>
            </Field>
            <Field label={t("sell.form.description")} span={2}>
              <textarea required value={form.description} onChange={(e) => set("description", e.target.value)} rows={6} className="w-full border border-[hsl(var(--line))] p-3 text-sm" placeholder={t("sell.form.description_placeholder")} data-testid="sell-description" />
            </Field>

            {err && <p className="md:col-span-2 text-sm text-[hsl(var(--danger))]" data-testid="sell-error">{err}</p>}

            <div className="md:col-span-2 flex flex-col sm:flex-row sm:items-center gap-3 sm:gap-4 mt-4">
              <button
                type="submit"
                disabled={loading}
                className="btn btn-primary w-full sm:w-auto !h-14 sm:!h-auto !text-base sm:!text-sm !px-8 sm:!px-6 font-semibold shadow-lg sm:shadow-none"
                data-testid="sell-submit"
              >
                {loading ? t("sell.submit_loading") : t("sell.submit_cta")}
              </button>
              <button
                type="button"
                onClick={() => setShowPreview(true)}
                disabled={!form.title || !form.make || !form.model}
                className="btn btn-secondary w-full sm:w-auto !h-14 sm:!h-auto !text-base sm:!text-sm !px-8 sm:!px-6"
                data-testid="sell-preview-btn"
              >
                {t("sell.preview_cta")}
              </button>
              <p className="text-xs text-[hsl(var(--ink-muted))]">{t("sell.photo_note")}</p>
            </div>
          </form>
        </div>
      </section>

      {showPreview && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-start justify-center p-4 overflow-auto" onClick={() => setShowPreview(false)} data-testid="sell-preview-modal">
          <div className="bg-white rounded-card max-w-3xl w-full my-10" onClick={(e) => e.stopPropagation()}>
            <div className="p-6 border-b border-[hsl(var(--line))] flex items-center justify-between">
              <div>
                <div className="overline text-[hsl(var(--accent))]">Преглед преди публикуване</div>
                <h2 className="font-serif text-2xl mt-1">Как ще изглежда вашата обява</h2>
              </div>
              <button onClick={() => setShowPreview(false)} className="text-sm text-[hsl(var(--ink-muted))] hover:text-[hsl(var(--ink))]">Затвори ✕</button>
            </div>
            <div className="p-6">
              {(form.images_exterior?.[0] || form.images?.[0]) && (
                <div className="aspect-[16/10] overflow-hidden rounded-card mb-5 bg-[hsl(var(--surface))]">
                  <img src={form.images_exterior?.[0] || form.images?.[0]} alt="" className="w-full h-full object-cover" />
                </div>
              )}
              <h3 className="font-serif text-3xl">{form.title || "Без заглавие"}</h3>
              <div className="mt-2 text-sm text-[hsl(var(--ink-muted))]">
                {form.year} · {form.make} {form.model} · {form.mileage_km} km · {form.fuel}
              </div>
              <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                <div className="p-3 border border-[hsl(var(--line))] rounded-card"><div className="text-[hsl(var(--ink-muted))]">Начална цена</div><div className="font-serif text-lg">{form.starting_bid_eur} €</div></div>
                <div className="p-3 border border-[hsl(var(--line))] rounded-card"><div className="text-[hsl(var(--ink-muted))]">Резерв</div><div className="font-serif text-lg">{form.no_reserve ? "Без" : (form.reserve_eur || "—")} {!form.no_reserve && form.reserve_eur ? "€" : ""}</div></div>
                <div className="p-3 border border-[hsl(var(--line))] rounded-card"><div className="text-[hsl(var(--ink-muted))]">ДДС</div><div className="font-serif text-lg">{form.vat_status === "vat_inclusive" ? "Неосв." : "Освоб."}</div></div>
                <div className="p-3 border border-[hsl(var(--line))] rounded-card"><div className="text-[hsl(var(--ink-muted))]">Време</div><div className="font-serif text-lg">{form.duration_days} дни</div></div>
              </div>
              {form.description && <p className="mt-5 text-sm whitespace-pre-line">{form.description}</p>}
              <div className="mt-6 flex items-center gap-3">
                <button onClick={() => setShowPreview(false)} className="btn btn-secondary">Назад за редакция</button>
                <button onClick={(e) => { setShowPreview(false); submit(e); }} className="btn btn-primary" data-testid="sell-preview-confirm">Потвърди и подай</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
