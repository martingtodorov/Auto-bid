import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth, formatError } from "../lib/auth";
import { api } from "../lib/apiClient";
import ImageUploader from "../components/ImageUploader";
import { CAR_MAKES } from "../lib/makes";

const FUELS = ["Бензин", "Дизел", "Хибриден", "Електрически", "Газ/Бензин"];
const TRANSMISSIONS = ["Автоматична", "Ръчна"];
const BODY_TYPES = ["Седан", "Комби", "Хечбек", "Джип", "Купе", "Кабрио", "Ван", "Пикап"];
const REGIONS = ["София", "Пловдив", "Варна", "Бургас", "Стара Загора", "Русе", "Плевен"];

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
    images_list: [],
    starting_bid_eur: 5000, reserve_eur: "",
    duration_days: 7,
  });
  const [err, setErr] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [loading, setLoading] = useState(false);

  const set = (k, v) => setForm((p) => ({ ...p, [k]: v }));

  const submit = async (e) => {
    e.preventDefault();
    if (!user) return navigate("/login?next=/sell");
    setErr(""); setLoading(true);
    try {
      const images = form.images_list || [];
      const payload = {
        ...form,
        images,
        year: Number(form.year),
        mileage_km: Number(form.mileage_km),
        power_hp: Number(form.power_hp),
        engine_cc: Number(form.engine_cc),
        starting_bid_eur: Number(form.starting_bid_eur),
        reserve_eur: form.reserve_eur ? Number(form.reserve_eur) : null,
        duration_days: Number(form.duration_days),
      };
      await api.post("/auctions", payload);
      setSubmitted(true);
    } catch (e) { setErr(formatError(e)); }
    finally { setLoading(false); }
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

          <form onSubmit={submit} className="mt-12 grid grid-cols-1 md:grid-cols-2 gap-5">
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
            <Field label="Снимки на автомобила (до 8)" span={2}>
              <ImageUploader images={form.images_list} onChange={(list) => set("images_list", list)} />
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
