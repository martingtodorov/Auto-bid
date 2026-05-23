import React, { useEffect, useState } from "react";
import { Navigate, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Phone, Bell, Trash2, BookmarkPlus } from "lucide-react";
import { useAuth, formatError } from "../lib/auth";
import { api } from "../lib/apiClient";
import TwoFactorSection from "../components/TwoFactorSection";
import PasskeySection from "../components/PasskeySection";
import PushSettings from "../components/PushSettings";
import EmailSettings from "../components/EmailSettings";
import SessionsSection from "../components/SessionsSection";
import SavedCardSection from "../components/SavedCardSection";
import AvatarSection from "../components/AvatarSection";
import { usePrivatePageMeta } from "../lib/usePrivatePageMeta";
import { useBrandName } from "../lib/brand";

export default function AccountSettingsPage() {
  const { t } = useTranslation();
  const brand = useBrandName();
  const { user, loading, refresh } = useAuth();
  const [phone, setPhone] = useState("");
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [searches, setSearches] = useState([]);
  usePrivatePageMeta({ titleKey: "page_meta.settings_title", descKey: "page_meta.settings_desc", brand });

  useEffect(() => {
    if (!user) return;
    setPhone(user.phone || "");
    loadSearches();
  }, [user]);

  const loadSearches = async () => {
    try { const { data } = await api.get("/me/saved-searches"); setSearches(data); }
    catch (e) { setSearches([]); }
  };

  if (loading) return <div className="py-24 text-center">{t("common.loading")}</div>;
  if (!user) return <Navigate to="/login?next=/settings" replace />;

  const save = async () => {
    setMsg(""); setErr(""); setSaving(true);
    try {
      // SMS notifications have been removed from the product entirely —
      // only phone (kept for invoice / KYC contact) is persisted here.
      // Push + email channels live in their own sections above.
      await api.patch("/me/profile", { phone: phone.trim() });
      await refresh();
      setMsg("Запазено");
      setTimeout(() => setMsg(""), 2000);
    } catch (e) { setErr(formatError(e)); }
    finally { setSaving(false); }
  };

  const removeSearch = async (id) => {
    await api.delete(`/me/saved-searches/${id}`);
    loadSearches();
  };

  const filterSummary = (f) => {
    const parts = [];
    if (f.q) parts.push(`„${f.q}"`);
    if (f.make) parts.push(f.make);
    if (f.body_type) parts.push(f.body_type);
    if (f.fuel) parts.push(f.fuel);
    if (f.region) parts.push(f.region);
    if (f.year_min) parts.push(`${t("settings.from", "от")} ${f.year_min}`);
    if (f.year_max) parts.push(`${t("settings.to", "до")} ${f.year_max}`);
    if (f.min_price) parts.push(`€${f.min_price}+`);
    if (f.max_price) parts.push(`${t("settings.to", "до")} €${f.max_price}`);
    return parts.length ? parts.join(" · ") : t("settings.no_filters", "Без филтри");
  };

  return (
    <main data-testid="settings-page">
      <div className="max-w-[900px] mx-auto px-4 sm:px-6 lg:px-10 py-16">
        <div className="overline text-[hsl(var(--accent))]">{t("settings.title", "Настройки")}</div>
        <h1 className="font-serif text-4xl lg:text-5xl mt-3 tracking-tight">{t("settings.headline", "Акаунт и известия")}</h1>

        <AvatarSection />

        {/* Notification preferences — placed right after the avatar section
            so users discover them immediately after creating their profile. */}
        <div className="mt-8 grid gap-6 lg:grid-cols-2">
          <PushSettings />
          <EmailSettings />
        </div>

        <section className="mt-12 rounded-card border border-[hsl(var(--line))] bg-white p-6 lg:p-8" data-testid="profile-section">
          <div className="flex items-center gap-3">
            <Phone size={18} className="text-[hsl(var(--accent))]" />
            <h2 className="font-serif text-2xl">{t("settings.phone_title", "Телефон за контакт")}</h2>
          </div>
          <p className="mt-3 text-sm text-[hsl(var(--ink-muted))]">{t("settings.phone_body", "Използваме телефона ви само за фактуриране и при нужда от свързване с вас за вече сключена сделка. Препоръчителен международен формат (+359...).")}</p>

          <div className="mt-6">
            <label className="overline text-[hsl(var(--ink-muted))] block mb-2">{t("settings.phone", "Телефон")}</label>
            <input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+359888123456" className="w-full max-w-sm border border-[hsl(var(--line))] h-11 px-3 text-sm" data-testid="phone-input" />
          </div>

          <div className="mt-6 flex items-center gap-4">
            <button onClick={save} disabled={saving} className="btn btn-primary" data-testid="save-profile">
              {saving ? t("settings.saving", "Запазване…") : t("settings.save", "Запази")}
            </button>
            {msg && <span className="text-sm text-[hsl(var(--accent))]">{msg}</span>}
            {err && <span className="text-sm text-[hsl(var(--danger))]" data-testid="profile-error">{err}</span>}
          </div>
        </section>

        <section className="mt-8 rounded-card border border-[hsl(var(--line))] bg-white p-6 lg:p-8" data-testid="saved-searches-section">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <Bell size={18} className="text-[hsl(var(--accent))]" />
              <h2 className="font-serif text-2xl">{t("settings.saved_searches_title", "Запазени търсения")}</h2>
            </div>
            <Link to="/auctions" className="text-xs underline text-[hsl(var(--ink-muted))] flex items-center gap-1">
              <BookmarkPlus size={12} /> {t("settings.add_from_search", "Добави от търсенето")}
            </Link>
          </div>
          <p className="mt-3 text-sm text-[hsl(var(--ink-muted))]">{t("settings.saved_searches_body", "Когато нова обява съвпадне с критериите ви, получавате имейл с линк директно към нея.")}</p>

          {searches.length === 0 ? (
            <div className="mt-6 py-10 text-center rounded-card bg-[hsl(var(--surface))] border border-dashed border-[hsl(var(--line))] text-sm text-[hsl(var(--ink-muted))]">
              {t("settings.saved_searches_empty", "Нямате запазени търсения. Отворете страницата за търгове, приложете филтри и натиснете „Запази търсенето\".")}
            </div>
          ) : (
            <div className="mt-6 space-y-3" data-testid="saved-searches-list">
              {searches.map((s) => (
                <div key={s.id} className="flex items-center justify-between gap-3 p-4 rounded-card border border-[hsl(var(--line))]" data-testid={`saved-search-${s.id}`}>
                  <div>
                    <div className="font-semibold text-sm">{s.name}</div>
                    <div className="text-xs text-[hsl(var(--ink-muted))] mt-1">{filterSummary(s.filters || {})}</div>
                  </div>
                  <button onClick={() => removeSearch(s.id)} className="text-[hsl(var(--ink-muted))] hover:text-[hsl(var(--danger))]" data-testid={`delete-search-${s.id}`}>
                    <Trash2 size={15} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </section>

        <TwoFactorSection />
        <PasskeySection />

        <SavedCardSection />

        <SessionsSection />

        <DangerZone />
      </div>
    </main>
  );
}

function DangerZone() {
  const { t } = useTranslation();
  const { user, logout } = useAuth();
  const [confirmText, setConfirmText] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const PHRASE = t("settings.delete_phrase", "ИЗТРИЙ");

  const onDelete = async () => {
    if (confirmText !== PHRASE) { setErr(t("settings.delete_confirm_err", "Въведете „{{p}}\" за потвърждение.", { p: PHRASE })); return; }
    if (!window.confirm(t("settings.delete_warn", "Това действие е необратимо. Продължаване?"))) return;
    setLoading(true); setErr("");
    try {
      await api.delete("/auth/me");
      logout();
      window.location.href = "/";
    } catch (e) { setErr(formatError(e)); }
    finally { setLoading(false); }
  };

  if (!user) return null;
  return (
    <section className="mt-8 rounded-card border-2 border-[hsl(var(--danger))]/40 bg-white p-6 lg:p-8" data-testid="danger-zone">
      <h2 className="font-serif text-2xl text-[hsl(var(--danger))]">{t("settings.delete_title", "Изтриване на акаунт (GDPR)")}</h2>
      <p className="mt-3 text-sm text-[hsl(var(--ink-muted))]">
        {t("settings.delete_body", "Правото ви на изтриване по GDPR. Ще премахнем вашите бидове, коментари, любими, запазени търсения, VIN заявки и отзиви. Вашите предишни обяви остават в историята на платформата като анонимизирани записи за целите на счетоводни/правни задължения.")}
      </p>
      <div className="mt-5">
        <label className="text-xs text-[hsl(var(--ink-muted))] uppercase tracking-wider">{t("settings.delete_phrase_label", "За потвърждение въведете „{{p}}\"", { p: PHRASE })}</label>
        <input value={confirmText} onChange={(e) => setConfirmText(e.target.value)} className="mt-1 w-full max-w-xs border border-[hsl(var(--line))] h-11 px-3 font-mono" data-testid="delete-account-confirm" />
      </div>
      {err && <p className="mt-3 text-sm text-[hsl(var(--danger))]" data-testid="delete-account-error">{err}</p>}
      <button onClick={onDelete} disabled={loading || confirmText !== PHRASE} className="mt-4 px-5 py-2.5 rounded-card bg-[hsl(var(--danger))] text-white text-sm disabled:opacity-50" data-testid="delete-account-btn">
        {loading ? t("settings.deleting", "Изтриване…") : t("settings.delete_cta", "Изтрий моя акаунт завинаги")}
      </button>
    </section>
  );
}
