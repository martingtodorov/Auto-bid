import React, { useEffect, useState } from "react";
import { CreditCard, Plus, Trash2, ShieldCheck, ExternalLink, Lock } from "lucide-react";
import { api } from "../lib/apiClient";
import { formatError } from "../lib/auth";

const BRAND_LABELS = {
  visa: "Visa",
  mastercard: "Mastercard",
  amex: "American Express",
  discover: "Discover",
  diners: "Diners Club",
  jcb: "JCB",
  unionpay: "UnionPay",
};

/**
 * Запазена карта (Stripe SetupIntent flow).
 * - Показва запазената карта с brand/last4/exp.
 * - "Добави карта" → отваря Stripe-hosted Checkout (mode=setup) и redirect.
 * - "Премахни" → detach в Stripe + изчистване в user документа.
 *
 * Post-redirect handling за `?stripe_setup_session_id=...` се прави в
 * AccountSettingsPage (parent), който вика `/cards/finalize`.
 */
export default function SavedCardSection() {
  const [card, setCard] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [okMsg, setOkMsg] = useState("");

  const load = async () => {
    setErr("");
    try {
      const { data } = await api.get("/stripe/cards/saved");
      setCard(data?.card || null);
    } catch (e) {
      setErr(formatError(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  // Финализиране след връщане от Stripe SetupIntent flow
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const sid = params.get("stripe_setup_session_id");
    const cancelled = params.get("stripe_setup_cancelled");
    if (cancelled) {
      setErr("Записването на картата бе отказано.");
      params.delete("stripe_setup_cancelled");
      window.history.replaceState({}, "", `${window.location.pathname}${params.toString() ? "?" + params : ""}`);
      return;
    }
    if (!sid) return;
    (async () => {
      try {
        const { data } = await api.post("/stripe/cards/finalize", { session_id: sid });
        setCard(data?.card || null);
        setOkMsg("Картата е успешно записана.");
      } catch (e) {
        setErr(formatError(e));
      } finally {
        params.delete("stripe_setup_session_id");
        window.history.replaceState({}, "", `${window.location.pathname}${params.toString() ? "?" + params : ""}`);
      }
    })();
  }, []);

  const addCard = async () => {
    setErr(""); setOkMsg(""); setBusy(true);
    try {
      const { data } = await api.post("/stripe/cards/setup-checkout", { origin: window.location.origin });
      if (data?.url) window.location.href = data.url;
    } catch (e) {
      setErr(formatError(e));
      setBusy(false);
    }
  };

  const removeCard = async () => {
    if (!window.confirm("Сигурни ли сте, че искате да премахнете запазената карта?")) return;
    setErr(""); setOkMsg(""); setBusy(true);
    try {
      await api.delete("/stripe/cards/saved");
      setCard(null);
      setOkMsg("Картата е премахната.");
    } catch (e) {
      setErr(formatError(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="mt-8 rounded-card border border-[hsl(var(--line))] bg-white p-6 lg:p-8" data-testid="saved-card-section">
      <div className="flex items-center gap-3">
        <CreditCard size={18} className="text-[hsl(var(--accent))]" />
        <h2 className="font-serif text-2xl">Запазена карта</h2>
      </div>
      <p className="mt-3 text-sm text-[hsl(var(--ink-muted))]">
        Запазете карта еднократно и наддавайте без redirect към Stripe всеки път. Картовите данни се обработват и съхраняват изцяло от Stripe — Auto&Bid никога не вижда номера на картата ви.
      </p>

      {loading ? (
        <div className="mt-6 py-10 text-center text-sm text-[hsl(var(--ink-muted))]">Зареждане…</div>
      ) : card ? (
        <div className="mt-6 rounded-card border border-[hsl(var(--accent))]/30 bg-[hsl(var(--accent-soft))] p-5 flex items-center justify-between gap-4 flex-wrap" data-testid="saved-card-active">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-card bg-white border border-[hsl(var(--line))] flex items-center justify-center">
              <CreditCard size={22} className="text-[hsl(var(--accent))]" />
            </div>
            <div>
              <div className="font-semibold" data-testid="saved-card-brand">
                {BRAND_LABELS[card.brand] || (card.brand ? card.brand[0].toUpperCase() + card.brand.slice(1) : "Карта")}
                {" "}•••• {card.last4 || "????"}
              </div>
              <div className="text-xs text-[hsl(var(--ink-muted))] mt-0.5" data-testid="saved-card-exp">
                Изтича {String(card.exp_month || "").padStart(2, "0")}/{String(card.exp_year || "").slice(-2)}
              </div>
            </div>
          </div>
          <button
            onClick={removeCard}
            disabled={busy}
            className="text-xs px-3 py-1.5 rounded-card border border-[hsl(var(--danger))]/40 text-[hsl(var(--danger))] hover:bg-[hsl(var(--danger))]/5 inline-flex items-center gap-1.5 disabled:opacity-50"
            data-testid="remove-saved-card"
          >
            <Trash2 size={13} /> Премахни
          </button>
        </div>
      ) : (
        <div className="mt-6">
          <div className="rounded-card border border-dashed border-[hsl(var(--line))] bg-[hsl(var(--surface))] p-6 text-center">
            <CreditCard size={28} className="mx-auto text-[hsl(var(--ink-muted))]" />
            <p className="mt-3 text-sm text-[hsl(var(--ink-muted))]">Все още нямате запазена карта.</p>
            <button
              onClick={addCard}
              disabled={busy}
              className="btn btn-accent mt-4 inline-flex items-center gap-2 disabled:opacity-50"
              data-testid="add-saved-card"
            >
              {busy ? <>Пренасочване…</> : <><Plus size={14} /> <ExternalLink size={12} /> Добави карта чрез Stripe</>}
            </button>
            <p className="mt-3 text-xs text-[hsl(var(--ink-muted))] flex items-center justify-center gap-1">
              <Lock size={10} /> Защитено от Stripe · никакви картови данни не се изпращат към наш сървър
            </p>
          </div>
        </div>
      )}

      {err && <p className="mt-4 text-sm text-[hsl(var(--danger))]" data-testid="saved-card-error">{err}</p>}
      {okMsg && (
        <p className="mt-4 text-sm text-[hsl(var(--accent))] flex items-center gap-1.5" data-testid="saved-card-ok">
          <ShieldCheck size={14} /> {okMsg}
        </p>
      )}
    </section>
  );
}
