import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import { CreditCard, Lock, X, ExternalLink, ShieldCheck } from "lucide-react";
import { api, formatEUR } from "../lib/apiClient";
import { formatError } from "../lib/auth";
import { useSiteSettings, computeBuyerFee } from "../lib/settings";

/**
 * Confirms the buyer's premium hold via Stripe Checkout.
 *
 * No card data is collected in our UI — we mint a Stripe Checkout Session
 * server-side (manual capture) and redirect the browser to Stripe's hosted
 * checkout page.  Funds are HELD on the card; capture happens only when the
 * bidder wins.  After Stripe completes, the user returns to the auction page
 * with `?stripe_session_id=...` and the bid can be placed.
 *
 * `onConfirm(paymentMethodId, last4)` is intentionally NOT called here — the
 * old flow returned a synthetic mock_pm_id directly.  In the new flow the
 * bid is placed only AFTER the Stripe redirect succeeds (see
 * AuctionDetailPage useEffect on `stripe_session_id`).
 */
export default function PreauthModal({ open, onClose, bidAmount, auctionId }) {
  const { t } = useTranslation();
  const settings = useSiteSettings();
  const [redirecting, setRedirecting] = useState(false);
  const [err, setErr] = useState("");

  if (!open) return null;
  const preauth = computeBuyerFee(bidAmount, settings);

  const startCheckout = async () => {
    setErr("");
    setRedirecting(true);
    try {
      // Pending bid info стои в localStorage за return-trip след Stripe
      // checkout, така че бидата да се пусне без нов user input.
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
      });
      if (data?.url) {
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

          <button onClick={startCheckout} disabled={redirecting} className="btn btn-accent w-full mt-6 inline-flex items-center justify-center gap-2" data-testid="preauth-confirm">
            <ExternalLink size={14} />
            {redirecting
              ? t("preauth.redirecting", "Пренасочване към Stripe…")
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
