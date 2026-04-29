import React, { useState, useEffect } from "react";
import { useTranslation, Trans } from "react-i18next";
import { X, Shield, Zap, ShieldCheck, ExternalLink, TrendingUp } from "lucide-react";
import { api, formatEUR } from "../lib/apiClient";
import { formatError } from "../lib/auth";
import { useSiteSettings, computeBuyerFee } from "../lib/settings";

export default function BiddingCreditModal({ auctionId, currentBid, currentCredit, onClose, onSaved }) {
  const { t } = useTranslation();
  const settings = useSiteSettings();

  // Fetch the server-computed next minimum bid (respects variable step schedule)
  const [nextMin, setNextMin] = useState(null);
  useEffect(() => {
    let cancelled = false;
    api.get(`/auctions/${auctionId}/next-bid`)
      .then((r) => { if (!cancelled) setNextMin(Number(r.data?.min_next_eur || 0)); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [auctionId]);

  // Minimum allowed credit: must cover at least the next valid bid, and when
  // increasing an existing credit must exceed the current max.
  const baseMin = nextMin != null ? nextMin : (currentBid || 0);
  const minAllowed = currentCredit
    ? Math.max(Math.floor(currentCredit.max_amount_eur) + 1, Math.ceil(baseMin))
    : Math.ceil(baseMin);

  const [amount, setAmount] = useState(() => {
    const seed = currentCredit?.max_amount_eur || Math.max(minAllowed + 5000, 10000);
    return Math.max(seed, minAllowed);
  });
  // If the server returns a higher min later, bump the input up automatically
  useEffect(() => {
    setAmount((prev) => (Number(prev) < minAllowed ? minAllowed : prev));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [minAllowed]);

  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [releasing, setReleasing] = useState(false);

  // Buyer's fee honoring the global min/max bounds (€150 / €4000 by default)
  const preauthAmount = computeBuyerFee(amount, settings);
  const pct = Number(settings?.buyer_fee_pct ?? 2);
  const feeMin = Number(settings?.buyer_fee_min_eur ?? 150);
  const feeMax = Number(settings?.buyer_fee_max_eur ?? 4000);

  /**
   * Stripe-first flow: новият или увеличеният кредит се потвърждава през
   * хоствана Stripe Checkout страница (manual capture).  Никакви картови
   * данни не се въвеждат тук.
   */
  const submit = async () => {
    setErr(""); setBusy(true);
    try {
      if (Number(amount) < minAllowed) {
        setErr(t("credit.err_below_min", { min: formatEUR(minAllowed) }));
        setBusy(false);
        return;
      }
      // Запазваме pending credit интента в localStorage за post-redirect
      // финализиране в AuctionDetailPage useEffect.
      try {
        localStorage.setItem(
          `pending_credit_${auctionId}`,
          JSON.stringify({ max_amount_eur: Number(amount), at: Date.now() })
        );
      } catch (_e) { /* ignore */ }
      const { data } = await api.post("/stripe/authorizations/create-checkout", {
        auction_id: auctionId,
        bidding_limit_eur: Number(amount),
        origin: window.location.origin,
      });
      if (data?.url) {
        window.location.href = data.url;
      } else {
        throw new Error("Stripe checkout URL липсва.");
      }
    } catch (e) {
      setErr(formatError(e));
      setBusy(false);
    }
  };

  const release = async () => {
    if (!window.confirm(t("credit.release_confirm"))) return;
    setErr(""); setReleasing(true);
    try {
      await api.delete(`/auctions/${auctionId}/bidding-credit`);
      onSaved && onSaved(null);
      onClose();
    } catch (e) { setErr(formatError(e)); }
    finally { setReleasing(false); }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4" data-testid="bidding-credit-modal">
      <div className="bg-white rounded-card w-full max-w-lg shadow-xl">
        <div className="flex items-center justify-between px-6 py-4 border-b border-[hsl(var(--line))]">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-full bg-[hsl(var(--accent-soft))] flex items-center justify-center text-[hsl(var(--accent))]">
              <Zap size={16} />
            </div>
            <h2 className="font-serif text-2xl">{currentCredit ? t("credit.title_increase") : t("credit.title_new")}</h2>
          </div>
          <button onClick={onClose} disabled={busy} className="p-2 hover:bg-[hsl(var(--surface))] rounded-full"><X size={18} /></button>
        </div>

        <div className="p-6 space-y-5">
          <div className="rounded-card bg-[hsl(var(--accent-soft))] border border-[hsl(var(--accent))]/20 p-4 text-sm leading-relaxed">
            <div className="flex items-start gap-2.5">
              <Shield size={16} className="text-[hsl(var(--accent))] shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold text-[hsl(var(--accent-ink))] mb-1">{t("credit.how_it_works")}</p>
                <p className="text-[hsl(var(--ink))]/80">
                  <Trans
                    i18nKey="credit.how_it_works_body"
                    values={{ pct, min: feeMin, max: feeMax }}
                    components={[<strong key="b" />]}
                  />
                </p>
              </div>
            </div>
          </div>

          {currentCredit && (
            <div className="rounded-card border border-[hsl(var(--line))] p-4 bg-[hsl(var(--surface))]">
              <div className="flex items-center justify-between">
                <div>
                  <div className="overline text-[hsl(var(--ink-muted))]">{t("credit.active_credit")}</div>
                  <div className="font-serif text-2xl mt-1">{formatEUR(currentCredit.max_amount_eur)}</div>
                </div>
                <div className="text-right">
                  <div className="overline text-[hsl(var(--ink-muted))]">{t("credit.blocked")}</div>
                  <div className="font-mono text-lg mt-1">{formatEUR(currentCredit.preauth_amount_eur)}</div>
                </div>
              </div>
            </div>
          )}

          <div>
            <label className="overline text-[hsl(var(--ink-muted))] block mb-2">
              {currentCredit ? t("credit.label_increase") : t("credit.label_new")}
            </label>
            <div className="relative">
              <input
                type="number"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                min={minAllowed}
                step={500}
                className="w-full border border-[hsl(var(--line))] h-14 px-4 text-2xl font-serif pr-12"
                data-testid="credit-amount-input"
              />
              <span className="absolute right-4 top-1/2 -translate-y-1/2 text-xl text-[hsl(var(--ink-muted))]">€</span>
            </div>
            <p className="mt-1.5 text-xs text-[hsl(var(--ink-muted))]">
              {t("credit.current_leading", { bid: formatEUR(currentBid), min: formatEUR(minAllowed) })}
            </p>
          </div>

          <div className="rounded-card border border-[hsl(var(--line))] p-4 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-sm text-[hsl(var(--ink-muted))] flex items-center gap-1.5">
                <TrendingUp size={13} /> {t("credit.preauth_label")}
              </span>
              <span className="font-serif text-xl">{formatEUR(preauthAmount)}</span>
            </div>
            <p className="text-xs text-[hsl(var(--ink-muted))]">
              {t("credit.preauth_hint")}
            </p>
          </div>

          {!currentCredit && (
            <div className="rounded-card border border-[hsl(var(--accent))]/20 bg-[hsl(var(--accent-soft))] p-3 flex items-start gap-2.5" data-testid="credit-stripe-notice">
              <ShieldCheck size={15} className="text-[hsl(var(--accent))] shrink-0 mt-0.5" />
              <div className="text-xs leading-relaxed text-[hsl(var(--ink))]/80">
                {t("credit.stripe_secure_body", "Картовите данни се въвеждат на защитената страница на Stripe. Никога не виждаме и не съхраняваме номера на картата.")}
              </div>
            </div>
          )}

          {err && <p className="text-sm text-[hsl(var(--danger))]" data-testid="credit-error">{err}</p>}

          <div className="flex items-center gap-2 pt-2">
            {currentCredit && (
              <button onClick={release} disabled={releasing || busy} className="btn btn-secondary !py-2.5 !px-4 text-sm !text-[hsl(var(--danger))] !border-[hsl(var(--danger))]/30" data-testid="credit-release">
                {releasing ? t("credit.releasing") : t("credit.release_cta")}
              </button>
            )}
            <div className="flex-1" />
            <button onClick={onClose} disabled={busy || releasing} className="btn btn-secondary">{t("credit.cancel")}</button>
            <button onClick={submit} disabled={busy || releasing} className="btn btn-accent flex items-center gap-2" data-testid="credit-submit">
              {busy ? (
                <>{t("credit.redirecting", "Пренасочване…")}</>
              ) : currentCredit ? (
                <><ExternalLink size={14} /> {t("credit.increase_cta")}</>
              ) : (
                <><ExternalLink size={14} /> {t("credit.block_cta", { amount: formatEUR(preauthAmount) })}</>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
