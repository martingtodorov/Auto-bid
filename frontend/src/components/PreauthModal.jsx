import React, { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { CreditCard, Lock, X, ExternalLink, ShieldCheck, Zap } from "lucide-react";
import { api, formatEUR } from "../lib/apiClient";
import { formatError } from "../lib/auth";
import { useSiteSettings, computeBuyerFee } from "../lib/settings";

/**
 * Confirms the buyer's premium hold via Stripe Checkout OR via a saved card
 * (Stripe SetupIntent + off-session PaymentIntent).
 *
 * No card data is collected in our UI — either Stripe Hosted Checkout collects
 * the PAN, or the previously-saved Stripe PaymentMethod is reused server-side.
 */
export default function PreauthModal({ open, onClose, bidAmount, auctionId, onPaidWithSavedCard }) {
  const { t } = useTranslation();
  const settings = useSiteSettings();
  const [redirecting, setRedirecting] = useState(false);
  const [savedCard, setSavedCard] = useState(null);
  const [loadingCard, setLoadingCard] = useState(true);
  const [err, setErr] = useState("");

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    (async () => {
      setLoadingCard(true);
      try {
        const { data } = await api.get("/stripe/cards/saved");
        if (!cancelled) setSavedCard(data?.card || null);
      } catch (_e) { /* graceful: just hide saved-card option */ }
      finally { if (!cancelled) setLoadingCard(false); }
    })();
    return () => { cancelled = true; };
  }, [open]);

  if (!open) return null;
  const preauth = computeBuyerFee(bidAmount, settings);

  const startCheckout = async ({ useSaved = false } = {}) => {
    setErr("");
    setRedirecting(true);
    try {
      // Pending bid info стои в localStorage за return-trip след Stripe checkout.
      try {
        localStorage.setItem(
          `pending_bid_${auctionId}`,
          JSON.stringify({ amount_eur: Number(bidAmount), at: Date.now() })
        );
      } catch (_e) { /* ignore */ }
      const { data } = await api.post("/stripe/authorizations/create-checkout", {
        auction_id: auctionId,
        bidding_limit_eur: Number(bidAmount),
        origin: window.location.origin,
        use_saved_card: !!useSaved,
      });
      if (data?.redirect === false && data?.id) {
        // Off-session success: hold-ът е активен, parent трябва да направи place-bid сега.
        setRedirecting(false);
        try { localStorage.removeItem(`pending_bid_${auctionId}`); } catch (_e) { /* ignore */ }
        if (onPaidWithSavedCard) onPaidWithSavedCard(data.id);
      } else if (data?.url) {
        window.location.href = data.url;
      } else {
        throw new Error("Stripe checkout URL липсва.");
      }
    } catch (e) {
      setErr(formatError(e));
      setRedirecting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[60] bg-black/50 backdrop-blur-sm flex items-center justify-center p-4" data-testid="preauth-modal">
      <div className="bg-white w-full max-w-md rounded-card border border-[hsl(var(--line))] overflow-hidden">
        <div className="p-5 flex items-center justify-between rule-b">
          <div className="flex items-center gap-2">
            <Lock size={16} />
            <span className="font-serif text-lg">{t("preauth.confirm_card", "Потвърди наддаването")}</span>
          </div>
          <button onClick={onClose} disabled={redirecting} data-testid="preauth-close"><X size={18} /></button>
        </div>

        <div className="p-6">
          <div className="rounded-card border border-[hsl(var(--line))] bg-[hsl(var(--surface))] p-4 flex items-center justify-between">
            <div>
              <div className="overline text-[hsl(var(--ink-muted))]">{t("preauth.buyer_fee")}</div>
              <div className="font-serif text-2xl mt-1">{formatEUR(preauth)}</div>
              <div className="text-xs text-[hsl(var(--ink-muted))] mt-1">
                {t("preauth.fee_detail", {
                  pct: settings.buyer_fee_pct,
                  min: settings.buyer_fee_min_eur,
                  max: settings.buyer_fee_max_eur,
                })}
              </div>
            </div>
            <CreditCard size={40} className="text-[hsl(var(--ink-muted))]" />
          </div>

          {!loadingCard && savedCard && (
            <div className="mt-5 rounded-card border border-[hsl(var(--accent))]/30 bg-[hsl(var(--accent-soft))] p-4 flex items-center justify-between gap-3" data-testid="preauth-saved-card">
              <div className="flex items-center gap-3">
                <CreditCard size={18} className="text-[hsl(var(--accent))]" />
                <div className="text-sm">
                  <div className="font-semibold">{savedCard.brand?.toUpperCase()} •••• {savedCard.last4}</div>
                  <div className="text-xs text-[hsl(var(--ink-muted))]">{t("preauth.saved_card_hint", "Запазена карта · без redirect")}</div>
                </div>
              </div>
              <button
                onClick={() => startCheckout({ useSaved: true })}
                disabled={redirecting}
                className="btn btn-accent !py-2 !px-3 text-xs inline-flex items-center gap-1.5"
                data-testid="preauth-pay-saved"
              >
                <Zap size={12} /> {redirecting ? t("preauth.processing", "Обработка…") : t("preauth.pay_saved_cta", "Наддай")}
              </button>
            </div>
          )}

          <div className="mt-5 rounded-card border border-[hsl(var(--accent))]/20 bg-[hsl(var(--accent-soft))] p-4 flex items-start gap-3" data-testid="preauth-stripe-notice">
            <ShieldCheck size={18} className="text-[hsl(var(--accent))] shrink-0 mt-0.5" />
            <div className="text-sm leading-relaxed">
              <p className="font-semibold text-[hsl(var(--accent-ink))] mb-1">{t("preauth.stripe_secure_title", "Сигурно през Stripe")}</p>
              <p className="text-[hsl(var(--ink))]/80">
                {t("preauth.stripe_secure_body", "Картовите данни се въвеждат на защитената страница на Stripe. {{brand}} никога не вижда и не съхранява номера на картата ви.", { brand: "Auto&Bid" })}
              </p>
            </div>
          </div>

          {err && <p className="mt-4 text-sm text-[hsl(var(--danger))]" data-testid="preauth-error">{err}</p>}

          <button onClick={() => startCheckout({ useSaved: false })} disabled={redirecting} className="btn btn-accent w-full mt-6 inline-flex items-center justify-center gap-2" data-testid="preauth-confirm">
            <ExternalLink size={14} />
            {redirecting
              ? t("preauth.redirecting", "Пренасочване към Stripe…")
              : savedCard
                ? t("preauth.authorize_other_cta", "Плати с друга карта · {{amount}}", { amount: formatEUR(preauth) })
                : t("preauth.authorize_cta", { amount: formatEUR(preauth) })}
          </button>
          <p className="text-xs text-center text-[hsl(var(--ink-muted))] mt-3 flex items-center justify-center gap-1">
            <Lock size={11} /> {t("preauth.powered_by_stripe", "Защитено плащане от Stripe")}
          </p>
        </div>
      </div>
    </div>
  );
}
