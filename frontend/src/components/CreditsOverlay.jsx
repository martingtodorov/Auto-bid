import React, { useEffect, useState, useCallback } from "react";
import { createPortal } from "react-dom";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { X, Wallet, Plus, Clock, ExternalLink } from "lucide-react";
import { api, formatEUR } from "../lib/apiClient";
import { formatError } from "../lib/auth";
import { auctionUrl } from "../lib/auctionUrl";
import TopUpCreditModal from "./TopUpCreditModal";

/**
 * CreditsOverlay — лесен достъп до акаунтния кредит пул от Nav.
 *
 * Backed by GET /api/stripe/authorizations/my-credits, който връща:
 *   • holds[]        — активни авторизации (могат да се отменят)
 *   • commitments[]  — текущи лидерски бидове (заключен кредит)
 *   • totals         — limit / hold / committed / available
 *
 * Действия:
 *   • "Зареди още" — отваря TopUpCreditModal (Stripe Checkout)
 *   • "Освободи" на конкретен hold — server enforces че може да се
 *     освободи само ако оставащият limit покрива committed.
 */
export default function CreditsOverlay({ onClose, onChanged }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState({});
  const [showTopUp, setShowTopUp] = useState(false);

  const load = useCallback(async () => {
    try {
      setErr("");
      const { data } = await api.get("/stripe/authorizations/my-credits");
      setSummary(data);
    } catch (e) {
      setErr(formatError(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Esc closes the overlay
  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const release = async (hold) => {
    if (!window.confirm(t("credit_overlay.release_confirm_v2",
      "Освободи {{lim}} от наддавателния кредит?", { lim: formatEUR(hold.bidding_limit_eur) }))) return;
    setBusy((b) => ({ ...b, [hold.authorization_id]: true }));
    try {
      await api.post(`/stripe/authorizations/${hold.authorization_id}/release`);
      await load();
      window.dispatchEvent(new Event("credits-updated"));
      onChanged && onChanged();
    } catch (e) {
      setErr(formatError(e));
    } finally {
      setBusy((b) => ({ ...b, [hold.authorization_id]: false }));
    }
  };

  return createPortal(
    <div
      className="fixed inset-0 z-[60] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4"
      data-testid="credits-overlay"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-card w-full max-w-lg max-h-[90vh] overflow-y-auto shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 bg-white flex items-center justify-between px-5 py-4 border-b border-[hsl(var(--line))] z-10">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-full bg-[hsl(var(--accent-soft))] flex items-center justify-center text-[hsl(var(--accent))]">
              <Wallet size={16} />
            </div>
            <h2 className="font-serif text-xl">{t("credit_overlay.title", "Наддавателен кредит")}</h2>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-[hsl(var(--surface))] rounded-full"
            data-testid="credits-overlay-close"
            aria-label={t("common.close", "Затвори")}
          >
            <X size={18} />
          </button>
        </div>

        <div className="p-5 space-y-4">
          {summary && (
            <div
              className="rounded-card border border-[hsl(var(--line))] p-4 bg-[hsl(var(--surface))] grid grid-cols-3 gap-3 text-center"
              data-testid="credits-overlay-totals"
            >
              <div>
                <div className="text-[10px] uppercase tracking-wide text-[hsl(var(--ink-muted))]">
                  {t("credit_overlay.available", "Налично")}
                </div>
                <div className="font-serif text-lg tabular-nums" data-testid="credits-overlay-available">
                  {formatEUR(summary.total_available_eur)}
                </div>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-wide text-[hsl(var(--ink-muted))]">
                  {t("credit_overlay.limit", "Лимит")}
                </div>
                <div className="font-serif text-lg tabular-nums">
                  {formatEUR(summary.total_limit_eur)}
                </div>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-wide text-[hsl(var(--ink-muted))]">
                  {t("credit_overlay.committed", "Ангажирано")}
                </div>
                <div className="font-serif text-lg tabular-nums">
                  {formatEUR(summary.total_committed_eur || 0)}
                </div>
              </div>
            </div>
          )}

          {err && (
            <div
              className="rounded-card border border-red-300 bg-red-50 text-red-800 px-4 py-3 text-sm"
              data-testid="credits-overlay-error"
            >
              {err}
            </div>
          )}

          <button
            type="button"
            onClick={() => setShowTopUp(true)}
            className="w-full btn btn-primary inline-flex items-center justify-center gap-1.5"
            data-testid="credits-overlay-topup-cta"
          >
            <Plus size={14} /> {t("credit_overlay.topup_cta", "Зареди още кредит")}
          </button>

          {loading ? (
            <div className="text-center text-[hsl(var(--ink-muted))] py-6">
              {t("common.loading", "Зарежда…")}
            </div>
          ) : (
            <>
              {summary && summary.commitments && summary.commitments.length > 0 && (
                <div className="space-y-2" data-testid="credits-overlay-commitments">
                  <h3 className="overline text-[hsl(var(--ink-muted))]">
                    {t("credit_overlay.committed_to", "Активни наддавания")}
                  </h3>
                  {summary.commitments.map((c) => (
                    <button
                      key={c.auction_id}
                      type="button"
                      onClick={() => { onClose(); navigate(auctionUrl({ id: c.auction_id, slug: c.auction_slug, title: c.auction_title })); }}
                      className="w-full text-left rounded-card border border-[hsl(var(--line))] p-3 hover:border-[hsl(var(--accent))] flex items-center gap-3"
                      data-testid={`credits-overlay-commit-${c.auction_id}`}
                    >
                      {c.auction_thumb && (
                        <img src={c.auction_thumb} alt="" className="w-14 h-10 object-cover rounded shrink-0" loading="lazy" />
                      )}
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-semibold line-clamp-1">{c.auction_title}</div>
                        <div className="text-xs text-[hsl(var(--ink-muted))] tabular-nums">
                          {formatEUR(c.current_bid_eur)} · <Clock size={9} className="inline" /> {new Date(c.ends_at).toLocaleDateString()}
                        </div>
                      </div>
                      <ExternalLink size={12} className="text-[hsl(var(--ink-muted))]" />
                    </button>
                  ))}
                </div>
              )}

              {summary && summary.holds && summary.holds.length > 0 && (
                <div className="space-y-2" data-testid="credits-overlay-holds">
                  <h3 className="overline text-[hsl(var(--ink-muted))]">
                    {t("credit_overlay.holds", "Авторизации на картата")}
                  </h3>
                  {summary.holds.filter((h) => h.authorization_status === "active").map((h) => (
                    <div
                      key={h.authorization_id}
                      className="rounded-card border border-[hsl(var(--line))] p-3 flex items-center justify-between gap-2"
                      data-testid={`credits-overlay-hold-${h.authorization_id}`}
                    >
                      <div>
                        <div className="text-sm font-semibold tabular-nums">
                          {formatEUR(h.bidding_limit_eur)}
                        </div>
                        <div className="text-[11px] text-[hsl(var(--ink-muted))]">
                          {t("credit_overlay.hold_blocked", "Блокирано: {{h}}", { h: formatEUR(h.hold_eur) })}
                          {h.created_at && ` · ${new Date(h.created_at).toLocaleDateString()}`}
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={() => release(h)}
                        disabled={busy[h.authorization_id]}
                        className="btn btn-secondary !py-1.5 !px-3 text-xs inline-flex items-center gap-1 !text-[hsl(var(--danger))] !border-[hsl(var(--danger))]/30"
                        data-testid={`credits-overlay-release-${h.authorization_id}`}
                      >
                        <X size={11} />
                        {busy[h.authorization_id] ? t("common.processing", "Обработва…") : t("credit_overlay.release", "Освободи")}
                      </button>
                    </div>
                  ))}
                </div>
              )}

              {summary && summary.count === 0 && (
                <div
                  className="text-center py-8 border border-dashed border-[hsl(var(--line))] rounded-card"
                  data-testid="credits-overlay-empty"
                >
                  <p className="text-sm text-[hsl(var(--ink-muted))]">
                    {t("credit_overlay.empty_v2", "Все още нямате авторизирани кредити. Заредете, за да започнете да наддавате.")}
                  </p>
                </div>
              )}
            </>
          )}

          <div className="flex items-center justify-between pt-2">
            <Link
              to="/my-bids"
              onClick={onClose}
              className="text-xs text-[hsl(var(--accent))] hover:underline"
              data-testid="credits-overlay-go-mybids"
            >
              {t("credit_overlay.full_page", "Пълен преглед →")}
            </Link>
            <button
              onClick={onClose}
              className="btn btn-secondary !py-2 !px-4 text-sm"
              data-testid="credits-overlay-close-bottom"
            >
              {t("common.close", "Затвори")}
            </button>
          </div>
        </div>
      </div>

      {showTopUp && (
        <TopUpCreditModal
          suggestedAmount={10000}
          onClose={() => setShowTopUp(false)}
        />
      )}
    </div>,
    document.body,
  );
}

