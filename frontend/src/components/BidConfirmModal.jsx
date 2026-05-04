import React, { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { X, Gavel, ShieldCheck, Plus, Wallet, AlertTriangle } from "lucide-react";
import { formatEUR } from "../lib/apiClient";

/**
 * BidConfirmModal — финално потвърждение преди наддаването е изпратено.
 *
 * След като user-ят натисне "Наддай" в auction страницата ние правим
 * предварителна валидация (има ли достатъчен кредит за стъпката).
 * Този overlay му показва крайните цифри и му позволява да:
 *   • Промени сумата (например ако случайно е въвел грешна цифра),
 *   • Зареди още кредит ако промененaта сума надхвърля наличния,
 *   • Потвърди и изпрати наддаването.
 *
 * Props:
 *   amountGross / amountNet  — началните стойности
 *   vatRate                  — % ДДС на обявата (0 ако е neutral)
 *   stepEur                  — минималната стъпка между бидове
 *   minNet                   — минимално допустимо нето наддаване
 *   accountCredit            — { total_available_eur, total_limit_eur, total_committed_eur }
 *   currentLeadByMe          — net amount user is currently leading with on this auction
 *   onConfirm(netAmount)     — parent submits the bid
 *   onTopUp(suggestedNet)    — parent opens TopUp modal with shortfall pre-filled
 *   onClose
 */
export default function BidConfirmModal({
  amountGross: initGross,
  amountNet: initNet,
  vatRate = 0,
  stepEur = 100,
  minNet = 0,
  accountCredit,
  currentLeadByMe = 0,
  onConfirm,
  onTopUp,
  onClose,
}) {
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);

  // The user can tweak the gross amount inside the overlay. We always
  // derive net from gross so the displayed VAT split stays consistent.
  const [gross, setGross] = useState(Number(initGross) || 0);
  const net = vatRate > 0 ? gross / (1 + vatRate / 100) : gross;

  // Re-sync if parent passes new initial values (e.g. after a top-up).
  useEffect(() => { setGross(Number(initGross) || 0); }, [initGross]);

  const available = Number(accountCredit?.total_available_eur || 0);
  const limit = Number(accountCredit?.total_limit_eur || 0);

  // Display amounts: the user types and reads in GROSS (incl. VAT) for
  // this auction. The credit pool is stored in NET on the backend, but
  // for *this* overlay we convert to gross terms so the math the user
  // sees matches what they're typing — €6,000 bid against a €X budget,
  // both in the same currency basis. Backend math on submit still uses
  // NET (`onConfirm(net)`).
  const vatMul = 1 + Number(vatRate || 0) / 100;
  const availableGross = available * vatMul;
  const limitGross = limit * vatMul;

  // The user's existing high bid on THIS auction is already committed
  // — adding to it only counts the *delta*. If they're not leading,
  // the entire net amount is fresh commit. We compute everything in
  // gross terms for display consistency with the typed amount.
  const delta = Math.max(0, net - currentLeadByMe);
  const deltaGross = delta * vatMul;
  const remaining = available - delta;
  const remainingGross = availableGross - deltaGross;
  const sufficient = remaining >= -0.5;
  const minGrossDisplay = vatRate > 0 ? Math.ceil(minNet * (1 + vatRate / 100)) : minNet;
  const belowMin = minNet > 0 && net < minNet - 0.5;

  const adjust = (signedStepGross) => {
    const next = Math.max(0, Number(gross) + signedStepGross);
    setGross(next);
  };

  const place = async () => {
    if (belowMin) return;
    if (!sufficient) {
      // Hand off to top-up flow. Suggest a gross-rounded amount so
      // the user sees the same currency basis they were typing in.
      const suggestedGross = Math.ceil(Math.abs(remainingGross) / 1000) * 1000;
      onTopUp && onTopUp(suggestedGross);
      return;
    }
    setBusy(true);
    try {
      await onConfirm(net);
      onClose();
    } finally {
      setBusy(false);
    }
  };

  // Step in gross terms — keeps the up/down arrows aligned with the
  // visible currency the user is editing.
  const stepGross = vatRate > 0 ? Math.round(stepEur * (1 + vatRate / 100)) : stepEur;

  return (
    <div
      className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4"
      data-testid="bid-confirm-modal"
    >
      <div className="bg-white rounded-card w-full max-w-md shadow-xl">
        <div className="flex items-center justify-between px-6 py-4 border-b border-[hsl(var(--line))]">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-full bg-[hsl(var(--accent-soft))] flex items-center justify-center text-[hsl(var(--accent))]">
              <Gavel size={16} />
            </div>
            <h2 className="font-serif text-2xl">
              {t("bid_confirm.title", "Потвърди наддаването")}
            </h2>
          </div>
          <button
            onClick={onClose}
            disabled={busy}
            className="p-2 hover:bg-[hsl(var(--surface))] rounded-full"
            data-testid="bid-confirm-close"
          >
            <X size={18} />
          </button>
        </div>

        <div className="p-6 space-y-5">
          {sufficient && !belowMin && (
            <div className="rounded-card border border-[hsl(var(--accent))]/30 bg-[hsl(var(--accent-soft))] p-4 flex items-start gap-2.5" data-testid="bid-confirm-ok-banner">
              <ShieldCheck size={16} className="text-[hsl(var(--accent))] shrink-0 mt-0.5" />
              <div className="text-sm text-[hsl(var(--ink))]/85">
                {t(
                  "bid_confirm.no_charge",
                  "Имате достатъчно наличен кредит — без ново плащане през Stripe."
                )}
              </div>
            </div>
          )}
          {!sufficient && (
            <div className="rounded-card border border-amber-300 bg-amber-50 p-4 flex items-start gap-2.5" data-testid="bid-confirm-shortfall-banner">
              <AlertTriangle size={16} className="text-amber-700 shrink-0 mt-0.5" />
              <div className="text-sm text-amber-900">
                {t("bid_confirm.shortfall",
                  "Недостигат {{amt}} от наличния кредит. Заредете още, за да наддадете.",
                  { amt: formatEUR(Math.abs(remainingGross)) })}
              </div>
            </div>
          )}
          {belowMin && (
            <div className="rounded-card border border-red-300 bg-red-50 p-3 text-sm text-red-800" data-testid="bid-confirm-below-min">
              {t("bid_confirm.below_min", "Минимално наддаване: {{min}}", { min: formatEUR(minGrossDisplay) })}
            </div>
          )}

          {/* Editable bid amount */}
          <div>
            <label className="overline text-[hsl(var(--ink-muted))] mb-1.5 block">
              {t("bid_confirm.your_bid", "Вашето наддаване")}
              {vatRate > 0 && <span className="ml-1 text-[10px] normal-case">({t("auction.incl_vat_label", "вкл. ДДС")} {vatRate}%)</span>}
            </label>
            <div className="flex items-stretch gap-1.5">
              <button
                type="button"
                onClick={() => adjust(-stepGross)}
                disabled={busy || gross <= stepGross}
                className="px-3 rounded-md border border-[hsl(var(--line))] hover:bg-[hsl(var(--surface))] text-lg disabled:opacity-40"
                data-testid="bid-confirm-decr"
              >−</button>
              <input
                type="number"
                value={Math.round(gross)}
                onChange={(e) => setGross(Number(e.target.value))}
                step={stepGross}
                min={minGrossDisplay || 0}
                disabled={busy}
                className="flex-1 border border-[hsl(var(--line))] rounded-md px-3 py-2 text-2xl font-mono text-right tabular-nums"
                data-testid="bid-confirm-amount-input"
              />
              <button
                type="button"
                onClick={() => adjust(stepGross)}
                disabled={busy}
                className="px-3 rounded-md border border-[hsl(var(--line))] hover:bg-[hsl(var(--surface))] text-lg disabled:opacity-40"
                data-testid="bid-confirm-incr"
              >+</button>
            </div>
            {vatRate > 0 && (
              <div className="text-[11px] text-[hsl(var(--ink-muted))] mt-1 flex justify-between">
                <span>{t("bid_confirm.net", "Нето (без ДДС)")}</span>
                <span className="tabular-nums" data-testid="bid-confirm-net">{formatEUR(net)}</span>
              </div>
            )}
          </div>

          <div className="rounded-card border border-[hsl(var(--line))] p-4 bg-[hsl(var(--surface))]" data-testid="bid-confirm-credit-summary">
            <div className="flex items-center gap-2 mb-2">
              <Wallet size={14} className="text-[hsl(var(--accent))]" />
              <span className="overline text-[hsl(var(--ink-muted))]">
                {t("bid_confirm.credit_summary", "Наддавателен кредит")}
              </span>
            </div>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <div className="text-xs text-[hsl(var(--ink-muted))]">
                  {t("bid_confirm.credit_available", "Налично сега")}
                </div>
                <div className="font-mono tabular-nums" data-testid="bid-confirm-available">
                  {formatEUR(availableGross)}
                  <span className="text-[10px] text-[hsl(var(--ink-muted))] ml-1">/ {formatEUR(limitGross)}</span>
                </div>
              </div>
              <div>
                <div className="text-xs text-[hsl(var(--ink-muted))]">
                  {t("bid_confirm.credit_after", "След това наддаване")}
                </div>
                <div className={`font-mono tabular-nums ${remainingGross < 0 ? "text-amber-700 font-semibold" : ""}`} data-testid="bid-confirm-remaining">
                  {formatEUR(Math.max(0, remainingGross))}
                </div>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2 pt-1">
            <button
              type="button"
              onClick={onClose}
              disabled={busy}
              className="btn btn-secondary flex-1"
              data-testid="bid-confirm-cancel"
            >
              {t("common.cancel", "Отказ")}
            </button>
            {!sufficient && (
              <button
                type="button"
                onClick={() => onTopUp && onTopUp(Math.ceil(Math.abs(remainingGross) / 1000) * 1000)}
                disabled={busy}
                className="btn btn-secondary flex-1 inline-flex items-center justify-center gap-1.5"
                data-testid="bid-confirm-topup"
              >
                <Plus size={13} /> {t("bid_confirm.topup", "Зареди още")}
              </button>
            )}
            <button
              type="button"
              onClick={place}
              disabled={busy || belowMin}
              className="btn btn-accent flex-1 inline-flex items-center justify-center gap-1.5 whitespace-nowrap"
              data-testid="bid-confirm-place"
            >
              {sufficient && !busy && <Gavel size={14} />}
              {busy
                ? t("bid_confirm.placing", "Наддаване…")
                : sufficient
                  ? t("bid_confirm.place_cta", "Наддай {{amt}}", { amt: formatEUR(gross) })
                  : t("bid_confirm.topup_then_bid", "Зареди и наддай")}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
