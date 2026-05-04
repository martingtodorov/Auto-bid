import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import { X, ShieldCheck, CreditCard, Wallet } from "lucide-react";
import { api, formatEUR } from "../lib/apiClient";
import { formatError } from "../lib/auth";
import { useSiteSettings, computeBuyerFee } from "../lib/settings";

/**
 * TopUpCreditModal — заявява account-level credit (не зависи от търг).
 *
 * Това замества стария per-auction `BiddingCreditModal`. Потребителят
 * избира общ лимит, ние блокираме policy-driven процент като platform
 * fee и записваме `bid_authorization` row с `auction_id=null` (виж
 * `routers/stripe_holds.py::topup_checkout`). След това лимитът може
 * да се ползва срещу който и да е активен търг.
 *
 * Props:
 *   suggestedAmount  — initial value (default 10000)
 *   onClose()
 *   onIssued(authId) — optional, fired when offsession path succeeds
 */
export default function TopUpCreditModal({ suggestedAmount = 10000, onClose, onIssued }) {
  const { t } = useTranslation();
  const settings = useSiteSettings();
  const [amount, setAmount] = useState(Math.max(1000, Number(suggestedAmount) || 10000));
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const fee = computeBuyerFee(amount, settings);
  const pct = Number(settings?.buyer_fee_pct ?? 2);
  const feeMin = Number(settings?.buyer_fee_min_eur ?? 150);
  const feeMax = Number(settings?.buyer_fee_max_eur ?? 4000);

  const submit = async () => {
    setErr(""); setBusy(true);
    try {
      if (Number(amount) <= 0) {
        setErr(t("topup.err_amount", "Сумата трябва да е положителна."));
        setBusy(false);
        return;
      }
      const { data } = await api.post("/stripe/authorizations/topup-checkout", {
        bidding_limit_eur: Number(amount),
        origin: window.location.origin,
      });
      if (data?.url) {
        // Stripe Checkout redirect — full-page navigation; once the
        // user returns, /my-credits picks up the active hold via the
        // polling-fallback in `_promote_pending_authorizations`.
        window.location.href = data.url;
        return;
      }
      // Defensive: server may return data without redirect for off-
      // session use (saved card) — in that case the hold is already
      // active and the parent should refresh the counter.
      window.dispatchEvent(new Event("credits-updated"));
      onIssued && onIssued(data?.id);
      onClose();
    } catch (e) {
      setErr(formatError(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[60] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4"
      data-testid="topup-modal"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-card w-full max-w-md shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-[hsl(var(--line))]">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-full bg-[hsl(var(--accent-soft))] flex items-center justify-center text-[hsl(var(--accent))]">
              <Wallet size={16} />
            </div>
            <h2 className="font-serif text-2xl">{t("topup.title", "Зареди наддавателен кредит")}</h2>
          </div>
          <button
            onClick={onClose}
            disabled={busy}
            className="p-2 hover:bg-[hsl(var(--surface))] rounded-full"
            data-testid="topup-close"
          >
            <X size={18} />
          </button>
        </div>

        <div className="p-6 space-y-5">
          <p className="text-sm text-[hsl(var(--ink-muted))]">
            {t("topup.subtitle",
              "Кредитът е универсален и може да се използва за наддаване на всеки активен търг. Не е свързан с конкретна обява.")}
          </p>

          <div>
            <label className="overline text-[hsl(var(--ink-muted))] mb-1 block">
              {t("topup.amount", "Желан кредит (€)")}
            </label>
            <input
              type="number"
              min={1000}
              step={1000}
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              className="w-full border border-[hsl(var(--line))] rounded-md px-3 py-2 text-lg font-mono"
              data-testid="topup-amount-input"
            />
          </div>

          <div className="rounded-card border border-[hsl(var(--accent))]/30 bg-[hsl(var(--accent-soft))] p-4 space-y-1.5">
            <div className="flex items-center gap-2 text-sm">
              <ShieldCheck size={14} className="text-[hsl(var(--accent))] shrink-0" />
              <span className="font-semibold">
                {t("topup.charge", "Stripe ще блокира {{fee}} ({{pct}}% от лимита)",
                  { fee: formatEUR(fee), pct })}
              </span>
            </div>
            <p className="text-xs text-[hsl(var(--ink-muted))] pl-6">
              {t("topup.charge_hint",
                "Само платформена комисионна се авторизира. Самата стойност на търга се урежда директно с продавача след спечелване.")}
            </p>
            <p className="text-[11px] text-[hsl(var(--ink-muted))] pl-6">
              {t("topup.bounds", "Минимум {{min}} · максимум {{max}}",
                { min: formatEUR(feeMin), max: formatEUR(feeMax) })}
            </p>
          </div>

          {err && (
            <div className="rounded-card border border-red-300 bg-red-50 text-red-800 px-4 py-2.5 text-sm" data-testid="topup-error">
              {err}
            </div>
          )}

          <div className="flex items-center gap-2 pt-1">
            <button
              type="button"
              onClick={onClose}
              disabled={busy}
              className="btn btn-secondary flex-1"
              data-testid="topup-cancel"
            >
              {t("common.cancel", "Отказ")}
            </button>
            <button
              type="button"
              onClick={submit}
              disabled={busy}
              className="btn btn-accent flex-1 inline-flex items-center justify-center gap-1.5"
              data-testid="topup-submit"
            >
              <CreditCard size={14} />
              {busy
                ? t("topup.processing", "Обработва…")
                : t("topup.cta", "Зареди през Stripe")}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
