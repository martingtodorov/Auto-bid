import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import { X, Gavel, ShieldCheck, Plus, Wallet } from "lucide-react";
import { formatEUR } from "../lib/apiClient";

/**
 * BidConfirmModal — shown when the user already has a bidding-credit that
 * covers their typed bid. No Stripe redirect needed; we just want a final
 * "yes I want to bid €X" confirmation, plus a shortcut to top up the
 * credit if the user wants more headroom for future bids.
 *
 * Props:
 *   amountGross   — what the user typed (incl. VAT if applicable)
 *   amountNet     — net amount that will actually be sent to the backend
 *   vatRate       — % VAT (0 if listing is VAT-neutral)
 *   credit        — { max_amount_eur, preauth_amount_eur }
 *   onConfirm()   — place the bid (parent handles api call)
 *   onTopUp()     — open BiddingCreditModal for limit increase
 *   onClose()
 */
export default function BidConfirmModal({
  amountGross,
  amountNet,
  vatRate = 0,
  credit,
  onConfirm,
  onTopUp,
  onClose,
}) {
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);

  const limit = Number(credit?.max_amount_eur || 0);
  const remaining = Math.max(0, limit - Number(amountNet || 0));

  const place = async () => {
    setBusy(true);
    try {
      await onConfirm();
      onClose();
    } finally {
      setBusy(false);
    }
  };

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
          <div className="rounded-card border border-[hsl(var(--accent))]/30 bg-[hsl(var(--accent-soft))] p-4 flex items-start gap-2.5">
            <ShieldCheck size={16} className="text-[hsl(var(--accent))] shrink-0 mt-0.5" />
            <div className="text-sm text-[hsl(var(--ink))]/85">
              {t(
                "bid_confirm.no_charge",
                "Имате достатъчно наличен кредит — без ново плащане през Stripe."
              )}
            </div>
          </div>

          <div className="rounded-card border border-[hsl(var(--line))] divide-y">
            <div className="flex items-center justify-between px-4 py-3">
              <span className="text-sm text-[hsl(var(--ink-muted))]">
                {t("bid_confirm.your_bid", "Вашето наддаване")}
              </span>
              <span
                className="font-serif text-2xl tabular-nums"
                data-testid="bid-confirm-gross"
              >
                {formatEUR(amountGross)}
              </span>
            </div>
            {vatRate > 0 && (
              <div className="flex items-center justify-between px-4 py-2.5 text-xs text-[hsl(var(--ink-muted))]">
                <span>{t("bid_confirm.net", "Нето (без ДДС)")}</span>
                <span className="tabular-nums" data-testid="bid-confirm-net">
                  {formatEUR(amountNet)}
                </span>
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
                  {t("bid_confirm.credit_limit", "Лимит")}
                </div>
                <div className="font-mono tabular-nums" data-testid="bid-confirm-limit">
                  {formatEUR(limit)}
                </div>
              </div>
              <div>
                <div className="text-xs text-[hsl(var(--ink-muted))]">
                  {t("bid_confirm.credit_remaining", "Остава след това наддаване")}
                </div>
                <div className="font-mono tabular-nums" data-testid="bid-confirm-remaining">
                  {formatEUR(remaining)}
                </div>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2 pt-1">
            <button
              type="button"
              onClick={onTopUp}
              disabled={busy}
              className="btn btn-secondary !py-2.5 !px-4 text-sm inline-flex items-center gap-1.5"
              data-testid="bid-confirm-topup"
            >
              <Plus size={13} /> {t("bid_confirm.topup", "Зареди още")}
            </button>
            <div className="flex-1" />
            <button
              type="button"
              onClick={onClose}
              disabled={busy}
              className="btn btn-secondary"
              data-testid="bid-confirm-cancel"
            >
              {t("common.cancel", "Отказ")}
            </button>
            <button
              type="button"
              onClick={place}
              disabled={busy}
              className="btn btn-accent flex items-center gap-2"
              data-testid="bid-confirm-place"
            >
              <Gavel size={14} />
              {busy
                ? t("bid_confirm.placing", "Наддаване…")
                : t("bid_confirm.place_cta", "Наддай {{amt}}", {
                    amt: formatEUR(amountGross),
                  })}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
