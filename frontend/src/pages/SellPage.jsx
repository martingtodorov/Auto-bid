import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth, formatError } from "../lib/auth";
import { api } from "../lib/apiClient";
import ImageUploader from "../components/ImageUploader";
import { CAR_MAKES } from "../lib/makes";

const FUELS = ["Бензин", "Дизел", "Хибриден", "Електрически", "Газ/Бензин"];
const TRANSMISSIONS = ["Автоматична", "Ръчна"];
const BODY_TYPES = ["Седан", "Комби", "Хечбек", "Джип", "Купе", "Кабрио", "Ван", "Пикап"];
const REGIONS = [
  "София (град)", "София (област)", "Пловдив", "Варна", "Бургас", "Русе",
  "Стара Загора", "Плевен", "Сливен", "Добрич", "Шумен", "Хасково",
  "Перник", "Ямбол", "Пазарджик", "Благоевград", "Велико Търново",
  "Враца", "Габрово", "Видин", "Монтана", "Кърджали", "Кюстендил",
  "Ловеч", "Разград", "Силистра", "Смолян", "Търговище",
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

export default function SellPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({
    title: "", make: "", model: "", year: 2020, mileage_km: 0,
    fuel: "Бензин", transmission: "Автоматична", body_type: "Седан",
    power_hp: 150, engine_cc: 2000, color: "",
    region: "София", city: "София", description: "",
    vin: "",
    contact_email: user?.email || "",
    contact_phone: "",
    images_exterior: [],
    images_wheels: [],
    images_bumper: [],
    images_interior: [],
    starting_bid_eur: 5000, reserve_eur: "",
    duration_days: 7,
  });
  const [err, setErr] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [loading, setLoading] = useState(false);

  // Prefill contact email once user loads
  useEffect(() => {
    if (user?.email) {
      setForm((p) => (p.contact_email ? p : { ...p, contact_email: user.email }));
    }
  }, [user]);

  const set = (k, v) => setForm((p) => ({ ...p, [k]: v }));

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
        setErr("Моля, попълнете имейл и телефон за контакт.");
        setLoading(false);
        return;
      }
      const phoneDigits = (form.contact_phone || "").replace(/[^\d]/g, "");
      if (phoneDigits.length < 7) {
        setErr("Моля, въведете валиден телефонен номер.");
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
        starting_bid_eur: Number(form.starting_bid_eur),
        reserve_eur: form.reserve_eur ? Number(form.reserve_eur) : null,
        duration_days: Number(form.duration_days),
        contact_email: form.contact_email.trim(),
        contact_phone: form.contact_phone.trim(),
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
          <div className="overline text-[hsl(var(--accent))]">Готово</div>
          <h1 className="font-serif text-4xl mt-3">Заявката е подадена</h1>
          <p className="mt-5 text-[hsl(var(--ink-muted))]">
            Нашият редакционен екип ще прегледа автомобила и ще се свърже с вас в рамките на 48 часа.
          </p>
          <button onClick={() => navigate("/")} className="btn btn-primary mt-8">Към началото</button>
        </div>
      </main>
    );
  }

  return (
    <main data-testid="sell-page">
      <section className="rule-b">
        <div className="max-w-[1100px] mx-auto px-4 sm:px-6 lg:px-10 py-16">
          <div className="overline text-[hsl(var(--accent))]">Продай автомобил</div>
          <h1 className="font-serif text-4xl lg:text-5xl tracking-tight mt-3">Подайте своя автомобил за търг</h1>
          <p className="mt-4 text-[hsl(var(--ink-muted))] max-w-2xl leading-relaxed">
            Попълнете подробностите по-долу. Нашият екип ще прегледа заявката, ще направи редакторски материал и ще стартира търга в рамките на 7 дни.
          </p>

          <div className="mt-10 rounded-card border border-[hsl(var(--accent))]/30 bg-[hsl(var(--accent-soft))] p-5" data-testid="mobile-bg-import">
            <div>
              <div className="overline text-[hsl(var(--accent))]">Бърз импорт от mobile.bg</div>
              <h3 className="font-serif text-xl mt-1.5">Имате обява в mobile.bg?</h3>
              <p className="text-sm text-[hsl(var(--ink))]/80 mt-1.5">
                Ще заредим автоматично марка, модел, година, пробег, гориво, цвят, описание и снимки. <strong>Цената и резервът задавате сами.</strong>
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
                {importing ? "Импортиране…" : "Импортирай данните"}
              </button>
            </div>
            {importMsg && <p className="mt-3 text-xs text-[hsl(var(--accent-ink))] font-semibold" data-testid="import-success">{importMsg}</p>}
            {importErr && <p className="mt-3 text-xs text-[hsl(var(--danger))]" data-testid="import-error">{importErr}</p>}
          </div>

          <form onSubmit={submit} className="mt-8 grid grid-cols-1 md:grid-cols-2 gap-5">
            <Field label="Заглавие" span={2}>
              <input required value={form.title} onChange={(e) => set("title", e.target.value)} className={inputCls} placeholder="Напр. Audi RS6 Avant Performance — Nardo Grey" data-testid="sell-title" />
            </Field>
            <Field label="Марка">
              <input required list="car-makes" value={form.make} onChange={(e) => set("make", e.target.value)} className={inputCls} placeholder="напр. BMW" data-testid="sell-make" />
              <datalist id="car-makes">
                {CAR_MAKES.map((m) => <option key={m} value={m} />)}
              </datalist>
            </Field>
            <Field label="Модел">
              <input required value={form.model} onChange={(e) => set("model", e.target.value)} className={inputCls} data-testid="sell-model" />
            </Field>
            <Field label="Година">
              <input type="number" required value={form.year} onChange={(e) => set("year", e.target.value)} className={inputCls} data-testid="sell-year" />
            </Field>
            <Field label="Пробег (км)">
              <input type="number" required value={form.mileage_km} onChange={(e) => set("mileage_km", e.target.value)} className={inputCls} data-testid="sell-mileage" />
            </Field>
            <Field label="Гориво">
              <select value={form.fuel} onChange={(e) => set("fuel", e.target.value)} className={inputCls} data-testid="sell-fuel">
                {FUELS.map((o) => <option key={o}>{o}</option>)}
              </select>
            </Field>
            <Field label="Скоростна кутия">
              <select value={form.transmission} onChange={(e) => set("transmission", e.target.value)} className={inputCls} data-testid="sell-transmission">
                {TRANSMISSIONS.map((o) => <option key={o}>{o}</option>)}
              </select>
            </Field>
            <Field label="Тип купе">
              <select value={form.body_type} onChange={(e) => set("body_type", e.target.value)} className={inputCls} data-testid="sell-body-type">
                {BODY_TYPES.map((o) => <option key={o}>{o}</option>)}
              </select>
            </Field>
            <Field label="Мощност (к.с.)">
              <input type="number" value={form.power_hp} onChange={(e) => set("power_hp", e.target.value)} className={inputCls} />
            </Field>
            <Field label="Обем (см³)">
              <input type="number" value={form.engine_cc} onChange={(e) => set("engine_cc", e.target.value)} className={inputCls} />
            </Field>
            <Field label="Цвят">
              <input value={form.color} onChange={(e) => set("color", e.target.value)} className={inputCls} />
            </Field>
            <Field label="Регион">
              <select value={form.region} onChange={(e) => set("region", e.target.value)} className={inputCls}>
                {REGIONS.map((o) => <option key={o}>{o}</option>)}
              </select>
            </Field>
            <Field label="Град">
              <input value={form.city} onChange={(e) => set("city", e.target.value)} className={inputCls} />
            </Field>
            <Field label="Начална цена (EUR)">
              <input type="number" required value={form.starting_bid_eur} onChange={(e) => set("starting_bid_eur", e.target.value)} className={inputCls} data-testid="sell-starting-bid" />
            </Field>
            <Field label="Резервна цена (EUR, незадължителна)">
              <input type="number" value={form.reserve_eur} onChange={(e) => set("reserve_eur", e.target.value)} className={inputCls} />
            </Field>
            <Field label="VIN номер (незадължителен, видим само на наддавачи)" span={2}>
              <input value={form.vin} onChange={(e) => set("vin", e.target.value.toUpperCase())} className={inputCls} maxLength={17} placeholder="напр. WAUZZZ4H9CN045678" data-testid="sell-vin" />
            </Field>
            <Field label="" span={2}>
              <div className="rounded-card border border-[hsl(var(--line))] bg-[hsl(var(--surface))] p-4">
                <div className="overline text-[hsl(var(--accent))] mb-1">Контакт с продавача</div>
                <p className="text-xs text-[hsl(var(--ink-muted))] mb-3">Нашият екип ще използва тези данни за потвърждение на обявата и организация на огледи. Телефонът и имейлът няма да са публични.</p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="overline text-[hsl(var(--ink-muted))] block mb-1.5">Имейл за контакт</label>
                    <input type="email" required value={form.contact_email} onChange={(e) => set("contact_email", e.target.value)} className={inputCls} placeholder="name@example.com" data-testid="sell-contact-email" />
                  </div>
                  <div>
                    <label className="overline text-[hsl(var(--ink-muted))] block mb-1.5">Телефонен номер</label>
                    <input type="tel" required value={form.contact_phone} onChange={(e) => set("contact_phone", e.target.value)} className={inputCls} placeholder="+359 88 888 8888" data-testid="sell-contact-phone" />
                  </div>
                </div>
              </div>
            </Field>
            <Field label="Снимки на автомобила" span={2}>
              <div className="space-y-3">
                <div className="text-xs text-[hsl(var(--ink-muted))] leading-relaxed">
                  Моля качете всички необходими снимки: <strong>минимум 8 екстериорни</strong>, <strong>4 на джанти</strong> (по една от всяка), <strong>1 на предната броня</strong>, <strong>4 интериорни</strong>. Първата екстериорна снимка се ползва като корица.
                </div>
                <ImageUploader
                  label="Екстериор"
                  helper="Снимки от всички страни на автомобила"
                  min={8}
                  max={20}
                  images={form.images_exterior}
                  onChange={(list) => set("images_exterior", list)}
                  testId="uploader-exterior"
                />
                <ImageUploader
                  label="Предна броня"
                  helper="Фронтално, за да се виждат евентуални забележки"
                  min={1}
                  max={4}
                  images={form.images_bumper}
                  onChange={(list) => set("images_bumper", list)}
                  testId="uploader-bumper"
                />
                <ImageUploader
                  label="Джанти"
                  helper="По една снимка на всяка джанта (общо 4)"
                  min={4}
                  max={8}
                  images={form.images_wheels}
                  onChange={(list) => set("images_wheels", list)}
                  testId="uploader-wheels"
                />
                <ImageUploader
                  label="Интериор"
                  helper="Волан, табло, седалки, заден ред"
                  min={4}
                  max={12}
                  images={form.images_interior}
                  onChange={(list) => set("images_interior", list)}
                  testId="uploader-interior"
                />
              </div>
            </Field>
            <Field label="Описание" span={2}>
              <textarea required value={form.description} onChange={(e) => set("description", e.target.value)} rows={6} className="w-full border border-[hsl(var(--line))] p-3 text-sm" placeholder="Разкажете историята на автомобила, оборудването и състоянието." data-testid="sell-description" />
            </Field>

            {err && <p className="md:col-span-2 text-sm text-[hsl(var(--danger))]" data-testid="sell-error">{err}</p>}

            <div className="md:col-span-2 flex items-center gap-4 mt-4">
              <button type="submit" disabled={loading} className="btn btn-primary" data-testid="sell-submit">
                {loading ? "Изпращане…" : "Подай за одобрение"}
              </button>
              <p className="text-xs text-[hsl(var(--ink-muted))]">След одобрение нашият екип ще направи професионален фото отчет.</p>
            </div>
          </form>
        </div>
      </section>
    </main>
  );
}
