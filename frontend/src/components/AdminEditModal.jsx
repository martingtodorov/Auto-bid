import React, { useState, useEffect } from "react";
import { X, Save, Image as ImageIcon, Plus, Trash2 } from "lucide-react";
import { api } from "../lib/apiClient";
import { formatError } from "../lib/auth";

const STATUS_OPTIONS = [
  { v: "pending", l: "Очаква одобрение" },
  { v: "live", l: "Активен" },
  { v: "ended", l: "Приключил" },
  { v: "sold", l: "Продаден" },
  { v: "reserve_not_met", l: "Резервът не е достигнат" },
  { v: "withdrawn", l: "Оттеглен" },
  { v: "removed", l: "Премахнат" },
  { v: "rejected", l: "Отказан" },
];

const FUEL_OPTIONS = ["Бензин", "Дизел", "Хибриден", "Електрически", "Газ", "Друг"];
const TRANSMISSION_OPTIONS = ["Ръчна", "Автоматична"];
const BODY_TYPE_OPTIONS = ["Седан", "Хечбек", "Комби", "Купе", "Кабрио", "Джип", "Ван", "Пикап"];

export default function AdminEditModal({ auctionId, onClose, onSaved }) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");
  const [form, setForm] = useState(null);
  const [newImageUrl, setNewImageUrl] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get(`/admin/auctions/${auctionId}`);
        const endsLocal = data.ends_at ? new Date(data.ends_at).toISOString().slice(0, 16) : "";
        setForm({ ...data, ends_at_local: endsLocal });
      } catch (e) { setErr(formatError(e)); }
      finally { setLoading(false); }
    })();
  }, [auctionId]);

  const set = (k, v) => setForm((p) => ({ ...p, [k]: v }));

  const addImageUrl = () => {
    const url = newImageUrl.trim();
    if (!url) return;
    set("images", [...(form.images || []), url]);
    setNewImageUrl("");
  };

  const removeImage = (idx) => set("images", (form.images || []).filter((_, i) => i !== idx));

  const handleFile = async (e) => {
    const files = Array.from(e.target.files || []);
    const readers = files.map((f) => new Promise((resolve) => {
      const r = new FileReader();
      r.onload = () => resolve(r.result);
      r.readAsDataURL(f);
    }));
    const dataUrls = await Promise.all(readers);
    set("images", [...(form.images || []), ...dataUrls]);
    e.target.value = "";
  };

  const save = async () => {
    setErr(""); setSaving(true);
    try {
      const payload = {
        title: form.title,
        description: form.description,
        make: form.make,
        model: form.model,
        year: form.year ? parseInt(form.year, 10) : null,
        mileage_km: form.mileage_km ? parseInt(form.mileage_km, 10) : null,
        fuel: form.fuel,
        transmission: form.transmission,
        body_type: form.body_type,
        power_hp: form.power_hp ? parseInt(form.power_hp, 10) : null,
        engine_cc: form.engine_cc ? parseInt(form.engine_cc, 10) : null,
        color: form.color,
        region: form.region,
        city: form.city,
        vin: form.vin || null,
        images: form.images || [],
        starting_bid_eur: form.starting_bid_eur !== "" && form.starting_bid_eur != null ? parseFloat(form.starting_bid_eur) : null,
        reserve_eur: form.reserve_eur !== "" && form.reserve_eur != null ? parseFloat(form.reserve_eur) : null,
        current_bid_eur: form.current_bid_eur !== "" && form.current_bid_eur != null ? parseFloat(form.current_bid_eur) : null,
        status: form.status,
        featured: !!form.featured,
        seller_name: form.seller_name,
      };
      if (form.ends_at_local) {
        payload.ends_at = new Date(form.ends_at_local).toISOString();
      }
      // Strip null values to avoid overwriting with null
      Object.keys(payload).forEach((k) => { if (payload[k] === null) delete payload[k]; });
      await api.put(`/admin/auctions/${auctionId}`, payload);
      onSaved && onSaved();
      onClose();
    } catch (e) { setErr(formatError(e)); }
    finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-start justify-center overflow-y-auto p-4" data-testid="admin-edit-modal">
      <div className="bg-white rounded-card w-full max-w-3xl my-8 shadow-xl">
        <div className="flex items-center justify-between px-6 py-4 border-b border-[hsl(var(--line))] sticky top-0 bg-white z-10">
          <h2 className="font-serif text-2xl">Редакция на обявата</h2>
          <button onClick={onClose} className="p-2 hover:bg-[hsl(var(--surface))] rounded-full" data-testid="admin-edit-close">
            <X size={18} />
          </button>
        </div>

        {loading && <div className="p-10 text-center text-sm text-[hsl(var(--ink-muted))]">Зареждане…</div>}
        {err && <div className="px-6 pt-4 text-sm text-[hsl(var(--danger))]">{err}</div>}

        {!loading && form && (
          <div className="p-6 space-y-6">
            <Section title="Основни данни">
              <Field label="Заглавие" full>
                <input type="text" value={form.title || ""} onChange={(e) => set("title", e.target.value)} className="input" data-testid="edit-title" />
              </Field>
              <Field label="Описание" full>
                <textarea value={form.description || ""} onChange={(e) => set("description", e.target.value)} rows={4} className="input" data-testid="edit-description" />
              </Field>
            </Section>

            <Section title="Автомобил">
              <Field label="Марка">
                <input type="text" value={form.make || ""} onChange={(e) => set("make", e.target.value)} className="input" data-testid="edit-make" />
              </Field>
              <Field label="Модел">
                <input type="text" value={form.model || ""} onChange={(e) => set("model", e.target.value)} className="input" data-testid="edit-model" />
              </Field>
              <Field label="Година">
                <input type="number" value={form.year || ""} onChange={(e) => set("year", e.target.value)} className="input" data-testid="edit-year" />
              </Field>
              <Field label="Пробег (км)">
                <input type="number" value={form.mileage_km ?? ""} onChange={(e) => set("mileage_km", e.target.value)} className="input" data-testid="edit-mileage" />
              </Field>
              <Field label="Гориво">
                <select value={form.fuel || ""} onChange={(e) => set("fuel", e.target.value)} className="input" data-testid="edit-fuel">
                  {FUEL_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}
                </select>
              </Field>
              <Field label="Скорости">
                <select value={form.transmission || ""} onChange={(e) => set("transmission", e.target.value)} className="input" data-testid="edit-transmission">
                  {TRANSMISSION_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}
                </select>
              </Field>
              <Field label="Каросерия">
                <select value={form.body_type || ""} onChange={(e) => set("body_type", e.target.value)} className="input" data-testid="edit-body-type">
                  {BODY_TYPE_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}
                </select>
              </Field>
              <Field label="Мощност (к.с.)">
                <input type="number" value={form.power_hp ?? ""} onChange={(e) => set("power_hp", e.target.value)} className="input" data-testid="edit-power" />
              </Field>
              <Field label="Обем (куб.см)">
                <input type="number" value={form.engine_cc ?? ""} onChange={(e) => set("engine_cc", e.target.value)} className="input" data-testid="edit-engine" />
              </Field>
              <Field label="Цвят">
                <input type="text" value={form.color || ""} onChange={(e) => set("color", e.target.value)} className="input" data-testid="edit-color" />
              </Field>
              <Field label="Регион">
                <input type="text" value={form.region || ""} onChange={(e) => set("region", e.target.value)} className="input" data-testid="edit-region" />
              </Field>
              <Field label="Град">
                <input type="text" value={form.city || ""} onChange={(e) => set("city", e.target.value)} className="input" data-testid="edit-city" />
              </Field>
              <Field label="VIN (17 символа)" full>
                <input type="text" value={form.vin || ""} onChange={(e) => set("vin", e.target.value.toUpperCase())} className="input font-mono" maxLength={17} data-testid="edit-vin" />
              </Field>
            </Section>

            <Section title="Цени и търг">
              <Field label="Начална цена (€)">
                <input type="number" value={form.starting_bid_eur ?? ""} onChange={(e) => set("starting_bid_eur", e.target.value)} className="input" data-testid="edit-starting-bid" />
              </Field>
              <Field label="Резервна цена (€)">
                <input type="number" value={form.reserve_eur ?? ""} onChange={(e) => set("reserve_eur", e.target.value)} className="input" data-testid="edit-reserve" />
              </Field>
              <Field label="Текуща водеща оферта (€)">
                <input type="number" value={form.current_bid_eur ?? ""} onChange={(e) => set("current_bid_eur", e.target.value)} className="input" data-testid="edit-current-bid" />
              </Field>
              <Field label="Край на търга">
                <input type="datetime-local" value={form.ends_at_local || ""} onChange={(e) => set("ends_at_local", e.target.value)} className="input" data-testid="edit-ends-at" />
              </Field>
              <Field label="Статус">
                <select value={form.status || ""} onChange={(e) => set("status", e.target.value)} className="input" data-testid="edit-status">
                  {STATUS_OPTIONS.map((o) => <option key={o.v} value={o.v}>{o.l}</option>)}
                </select>
              </Field>
              <Field label="Продавач (име)">
                <input type="text" value={form.seller_name || ""} onChange={(e) => set("seller_name", e.target.value)} className="input" data-testid="edit-seller-name" />
              </Field>
              <Field label="" full>
                <label className="flex items-center gap-3 text-sm">
                  <input type="checkbox" checked={!!form.featured} onChange={(e) => set("featured", e.target.checked)} data-testid="edit-featured" />
                  Промотирана обява (на началната страница)
                </label>
              </Field>
            </Section>

            <Section title="Снимки">
              <div className="col-span-full">
                {(form.images || []).length > 0 && (
                  <div className="grid grid-cols-3 sm:grid-cols-4 gap-3 mb-4" data-testid="edit-images-grid">
                    {form.images.map((src, i) => (
                      <div key={i} className="relative aspect-square bg-[hsl(var(--surface))] rounded-md overflow-hidden">
                        <img src={src} alt="" className="w-full h-full object-cover" />
                        <button onClick={() => removeImage(i)} className="absolute top-1 right-1 bg-black/70 text-white p-1 rounded-full" data-testid={`remove-image-${i}`}>
                          <Trash2 size={12} />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={newImageUrl}
                    onChange={(e) => setNewImageUrl(e.target.value)}
                    placeholder="URL на снимка"
                    className="input flex-1"
                    data-testid="edit-image-url"
                  />
                  <button onClick={addImageUrl} className="btn btn-secondary !py-2 !px-3 flex items-center gap-1" data-testid="edit-add-image-url">
                    <Plus size={14} /> URL
                  </button>
                  <label className="btn btn-secondary !py-2 !px-3 flex items-center gap-1 cursor-pointer">
                    <ImageIcon size={14} /> Файл
                    <input type="file" accept="image/*" multiple onChange={handleFile} className="hidden" data-testid="edit-image-file" />
                  </label>
                </div>
              </div>
            </Section>

            <div className="flex justify-end gap-2 pt-4 border-t border-[hsl(var(--line))]">
              <button onClick={onClose} className="btn btn-secondary" disabled={saving}>Отказ</button>
              <button onClick={save} disabled={saving} className="btn btn-primary flex items-center gap-2" data-testid="edit-save">
                <Save size={14} /> {saving ? "Запазване…" : "Запази промените"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div>
      <div className="overline text-[hsl(var(--accent))] mb-3">{title}</div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {children}
      </div>
    </div>
  );
}

function Field({ label, children, full = false }) {
  return (
    <div className={full ? "sm:col-span-2" : ""}>
      {label && <label className="overline text-[hsl(var(--ink-muted))] block mb-1.5">{label}</label>}
      {children}
    </div>
  );
}
