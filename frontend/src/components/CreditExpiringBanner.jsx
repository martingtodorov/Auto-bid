import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { CreditCard, AlertTriangle } from "lucide-react";
import { api } from "../lib/apiClient";
import { useAuth } from "../lib/auth";

/**
 * Banner that surfaces when the lifecycle worker couldn't auto-extend
 * an account-level credit hold within 24 hours of expiry. We poll
 * `/stripe/authorizations/expiring` once on mount + every 10 min so
 * the banner appears without a hard reload.
 *
 * The user can:
 *   • Click "Add card" → /settings (Stripe SetupIntent flow saves a PM)
 *   • Click "Top up" → /my-bids (TopUpCreditModal)
 *
 * Banner is dismissible per-session (localStorage key) so it's not
 * stuck in front of the user all day. After a fresh login it returns
 * if the underlying state is still "expiring".
 */
const DISMISS_KEY = "ab.credit_expiring_dismissed_until";

export default function CreditExpiringBanner() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [state, setState] = useState(null);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    if (!user) return;
    // Honour a fresh dismissal for 12h.
    try {
      const until = Number(localStorage.getItem(DISMISS_KEY) || 0);
      if (until > Date.now()) { setDismissed(true); return; }
    } catch (e) {}
    let cancelled = false;
    const load = async () => {
      try {
        const { data } = await api.get("/stripe/authorizations/expiring");
        if (!cancelled) setState(data);
      } catch (e) {}
    };
    load();
    const interval = setInterval(load, 10 * 60 * 1000);  // 10 min
    return () => { cancelled = true; clearInterval(interval); };
  }, [user]);

  if (!user || !state || !state.has_expiring || dismissed) return null;

  const dismiss = () => {
    setDismissed(true);
    try { localStorage.setItem(DISMISS_KEY, String(Date.now() + 12 * 3600 * 1000)); } catch (e) {}
  };

  // Pick the right copy based on *why* extension failed. Default
  // (state.reason === null) means we haven't tried yet — we still warn
  // proactively because expiration is < 24h away regardless.
  const reasonKey = state.reason === "card_declined"
    ? "credit_expiring.body_declined"
    : state.reason === "no_saved_pm"
      ? "credit_expiring.body_no_pm"
      : "credit_expiring.body_default";
  const reasonDefault = state.reason === "card_declined"
    ? "Картата ви отхвърли подновяването. Кредитът изтича след 24 часа — обновете картата."
    : state.reason === "no_saved_pm"
      ? "Кредитът ви изтича след 24 часа. Добавете карта, за да продължите да наддавате."
      : "Кредитът ви изтича скоро. Добавете карта, за да го подновим автоматично.";

  return (
    <div
      className="bg-red-50 border-b border-red-200 text-red-900"
      data-testid="credit-expiring-banner"
    >
      <div className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-10 py-2.5 flex items-center justify-between gap-4 text-sm flex-wrap">
        <div className="flex items-center gap-2 min-w-0">
          <AlertTriangle size={16} className="shrink-0" />
          <span className="truncate">{t(reasonKey, reasonDefault)}</span>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          <Link
            to="/settings"
            className="px-3 py-1 rounded-card bg-red-700 text-white text-xs font-semibold inline-flex items-center gap-1.5 hover:bg-red-800"
            data-testid="credit-expiring-add-card"
          >
            <CreditCard size={12} />
            {t("credit_expiring.add_card_cta", "Добави карта")}
          </Link>
          <button
            onClick={dismiss}
            className="text-xs text-red-800/70 hover:text-red-900 underline"
            data-testid="credit-expiring-dismiss"
          >
            {t("credit_expiring.dismiss", "По-късно")}
          </button>
        </div>
      </div>
    </div>
  );
}
