import React, { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Lock, Shield, Zap } from "lucide-react";
import { api, formatEUR } from "../lib/apiClient";
import { useAuth } from "../lib/auth";

/** Authorize-bidding card.
 *
 * Shows the user's currently active hold (if any) and otherwise lets them
 * authorize a card for an upper bidding limit. We NEVER collect card data —
 * we just redirect the browser to Stripe-hosted Checkout.
 */
export default function StripeAuthorize({ auctionId, suggestedLimit = 10000 }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [active, setActive] = useState(null);
  const [limit, setLimit] = useState(suggestedLimit);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const refresh = async () => {
    if (!user) return;
    try {
      const { data } = await api.get(`/stripe/authorizations/active`, { params: { auction_id: auctionId } });
      setActive(data && data.id ? data : null);
    } catch (e) {}
  };

  useEffect(() => { refresh(); }, [auctionId, user]);

  // After Stripe redirects back with ?stripe_session_id=…, just refresh.
  useEffect(() => {
    const sp = new URLSearchParams(window.location.search);
    if (sp.get("stripe_session_id")) {
      const t1 = setTimeout(refresh, 1500);
      const t2 = setTimeout(refresh, 4000);
      return () => { clearTimeout(t1); clearTimeout(t2); };
    }
  }, []);

  const startCheckout = async () => {
    setError("");
    setBusy(true);
    try {
      const { data } = await api.post(`/stripe/authorizations/create-checkout`, {
        auction_id: auctionId,
        bidding_limit_eur: Number(limit),
        origin: window.location.origin,
      });
      // Hosted Stripe Checkout — card data lives entirely on stripe.com.
      window.location.href = data.url;
    } catch (e) {
      setError(e?.response?.data?.detail || String(e));
      setBusy(false);
    }
  };

  if (!user) return null;

  if (active && active.authorization_status === "active") {
    return (
      <div className="rounded-card border border-[hsl(var(--accent))]/30 bg-[hsl(var(--accent-soft))]/40 p-4" data-testid="stripe-active-auth">
        <div className="flex items-start gap-2">
          <Shield size={16} className="text-[hsl(var(--accent))] shrink-0 mt-0.5" />
          <div className="flex-1">
            <div className="font-semibold text-sm text-[hsl(var(--accent-ink))]">
              {t("stripe.active_title", "Активна авторизация")}
            </div>
            <div className="text-xs text-[hsl(var(--ink-muted))] mt-0.5">
              {t("stripe.active_body", "Лимит за наддаване: {{limit}} · Блокирани: {{hold}}", {
                limit: formatEUR(active.bidding_limit_eur),
                hold: formatEUR(active.amount_authorized_eur),
              })}
            </div>
            <div className="text-[10px] text-[hsl(var(--ink-muted))] mt-1 font-mono">
              {t("stripe.expires_at", "Валидна до")}: {new Date(active.authorization_expires_at).toLocaleString()}
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-card border border-[hsl(var(--line))] bg-[hsl(var(--surface))] p-4" data-testid="stripe-authorize-card">
      <div className="flex items-start gap-2 mb-3">
        <Lock size={14} className="text-[hsl(var(--ink-muted))] shrink-0 mt-0.5" />
        <div>
          <div className="font-semibold text-sm">{t("stripe.authorize_title", "Активирай наддаване")}</div>
          <div className="text-xs text-[hsl(var(--ink-muted))] mt-0.5">
            {t("stripe.authorize_hint", "Картата се обработва от Stripe — никога не я виждаме. Блокираме малък процент от лимита съгласно настройките на платформата.")}
          </div>
        </div>
      </div>
      <label className="overline text-[hsl(var(--ink-muted))] block mb-1.5">
        {t("stripe.limit_label", "Максимално наддаване (EUR)")}
      </label>
      <input
        type="number"
        min={500}
        step={500}
        value={limit}
        onChange={(e) => setLimit(e.target.value)}
        className="w-full border border-[hsl(var(--line))] h-11 px-3 text-sm bg-white"
        data-testid="stripe-limit-input"
      />
      <button
        onClick={startCheckout}
        disabled={busy || !limit || Number(limit) < 500}
        className="mt-3 w-full btn btn-primary flex items-center justify-center gap-2 disabled:opacity-50"
        data-testid="stripe-authorize-btn"
      >
        <Zap size={14} />
        {busy ? t("stripe.processing", "Пренасочваме към Stripe…") : t("stripe.authorize_action", "Авторизирай чрез Stripe →")}
      </button>
      {error && <p className="text-xs text-[hsl(var(--danger))] mt-2" data-testid="stripe-error">{error}</p>}
    </div>
  );
}
