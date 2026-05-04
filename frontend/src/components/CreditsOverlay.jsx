import React, { useEffect, useState, useCallback } from "react";
import { createPortal } from "react-dom";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { X, Wallet, Plus, Trophy, Clock, ExternalLink } from "lucide-react";
import { api, formatEUR } from "../lib/apiClient";
import { formatError } from "../lib/auth";
import { auctionUrl } from "../lib/auctionUrl";

/**
 * CreditsOverlay — quick-action sheet wired to the Nav credit counter.
 *
 * Shows the same data as `/my-bids` but as a modal so users can
 * cancel/top-up holds without losing their current page context.
 *
 *   • Releases holds where the user is NOT currently leading (server
 *     enforces the same rule and rejects 409 if the user races into
 *     leading mid-click).
 *   • "Зареди още" deep-links to the auction's bid form for any held
 *     auction (top-up via BiddingCreditModal there).
 *   • If there are no holds, shows a CTA to browse auctions.
 *
 * Data source: GET /api/stripe/authorizations/my-credits — same
 * endpoint that powers the Nav counter, so the totals always match.
 */
export default function CreditsOverlay({ onClose, onChanged }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState({}); // {auth_id: true}

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
    if (hold.is_leading && hold.auction_status === "live") {
      // Server will refuse with 409 — surface a clear pre-emptive
      // confirmation instead of letting the click fail silently.
      if (!window.confirm(t("credit_overlay.release_warning",
        "Вие сте текущ лидер на този търг — авторизацията не може да се отмени, докато водите."))) return;
    } else {
      if (!window.confirm(t("credit_overlay.release_confirm",
        "Освобождаване на авторизация за {{title}}?", { title: hold.auction_title }))) return;
    }
    setBusy((b) => ({ ...b, [hold.authorization_id]: true }));
    try {
      await api.post(`/stripe/authorizations/${hold.authorization_id}/release`);
      await load();
      // Tell the nav counter to refresh — without this the counter
      // stays stuck on the old value for up to 90 s after a release.
      window.dispatchEvent(new Event("credits-updated"));
      onChanged && onChanged();
    } catch (e) {
      setErr(formatError(e));
    } finally {
      setBusy((b) => ({ ...b, [hold.authorization_id]: false }));
    }
  };

  const topUp = (hold) => {
    onClose();
    const link = auctionUrl({
      id: hold.auction_id,
      slug: hold.auction_slug,
      title: hold.auction_title,
    });
    navigate(`${link}?bid=1`);
  };

  return createPortal(
    <div
      className="fixed inset-0 z-[60] bg-black/60 backdrop-blur-sm flex items-end sm:items-center justify-center p-0 sm:p-4"
      data-testid="credits-overlay"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-t-card sm:rounded-card w-full max-w-lg max-h-[90vh] overflow-y-auto shadow-xl"
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
          {summary && summary.count > 0 && (
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
                  {t("credit_overlay.held", "Блокирано")}
                </div>
                <div className="font-serif text-lg tabular-nums">
                  {formatEUR(summary.total_hold_eur)}
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

          {loading ? (
            <div className="text-center text-[hsl(var(--ink-muted))] py-6">
              {t("common.loading", "Зарежда…")}
            </div>
          ) : !summary || summary.count === 0 ? (
            <div
              className="text-center py-10 border border-dashed border-[hsl(var(--line))] rounded-card"
              data-testid="credits-overlay-empty"
            >
              <Wallet size={28} className="mx-auto text-[hsl(var(--ink-muted))] mb-3" />
              <p className="font-serif text-lg mb-1">
                {t("credit_overlay.empty_title", "Няма активни авторизации")}
              </p>
              <p className="text-sm text-[hsl(var(--ink-muted))] mb-4">
                {t("credit_overlay.empty_body", "Авторизирайте карта на който и да е активен търг.")}
              </p>
              <Link
                to="/auctions"
                onClick={onClose}
                className="btn btn-primary"
                data-testid="credits-overlay-browse"
              >
                {t("credit_overlay.browse", "Разгледай търгове")}
              </Link>
            </div>
          ) : (
            <div className="space-y-2.5" data-testid="credits-overlay-holds">
              {summary.holds.map((h) => {
                const ended = h.auction_status && h.auction_status !== "live" && h.auction_status !== "scheduled";
                const canRelease = !h.is_leading || ended;
                return (
                  <div
                    key={h.authorization_id}
                    className="rounded-card border border-[hsl(var(--line))] p-3"
                    data-testid={`credits-overlay-row-${h.auction_id}`}
                  >
                    <div className="flex items-start gap-3">
                      {h.auction_thumb && (
                        <Link
                          to={auctionUrl({ id: h.auction_id, slug: h.auction_slug, title: h.auction_title })}
                          onClick={onClose}
                          className="shrink-0"
                        >
                          <img src={h.auction_thumb} alt="" className="w-16 h-12 object-cover rounded" loading="lazy" />
                        </Link>
                      )}
                      <div className="flex-1 min-w-0">
                        <Link
                          to={auctionUrl({ id: h.auction_id, slug: h.auction_slug, title: h.auction_title })}
                          onClick={onClose}
                          className="text-sm font-semibold line-clamp-1 hover:text-[hsl(var(--accent))]"
                        >
                          {h.auction_title}
                        </Link>
                        <div className="flex items-center gap-3 mt-1 text-[11px]">
                          {h.is_leading ? (
                            <span className="inline-flex items-center gap-1 text-emerald-700 font-semibold">
                              <Trophy size={10} /> {t("credit_overlay.leading", "Водите")}
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 text-amber-700">
                              <Clock size={10} /> {t("credit_overlay.outbid", "Надминат")}
                            </span>
                          )}
                          <span className="text-[hsl(var(--ink-muted))] tabular-nums">
                            {formatEUR(h.available_eur)} / {formatEUR(h.bidding_limit_eur)}
                          </span>
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 mt-3 flex-wrap">
                      <button
                        type="button"
                        onClick={() => topUp(h)}
                        className="btn btn-primary !py-1.5 !px-3 text-xs inline-flex items-center gap-1"
                        data-testid={`credits-overlay-topup-${h.auction_id}`}
                      >
                        <Plus size={11} /> {t("credit_overlay.topup", "Зареди още")}
                      </button>
                      <button
                        type="button"
                        onClick={() => { onClose(); navigate(auctionUrl({ id: h.auction_id, slug: h.auction_slug, title: h.auction_title })); }}
                        className="btn btn-secondary !py-1.5 !px-3 text-xs inline-flex items-center gap-1"
                        data-testid={`credits-overlay-view-${h.auction_id}`}
                      >
                        <ExternalLink size={11} /> {t("credit_overlay.view", "Виж търга")}
                      </button>
                      <button
                        type="button"
                        onClick={() => release(h)}
                        disabled={busy[h.authorization_id]}
                        className={`btn !py-1.5 !px-3 text-xs inline-flex items-center gap-1 ${canRelease ? "btn-secondary !text-[hsl(var(--danger))] !border-[hsl(var(--danger))]/30" : "btn-secondary opacity-60"}`}
                        data-testid={`credits-overlay-release-${h.auction_id}`}
                        title={canRelease
                          ? t("credit_overlay.release_hint", "Освобождава 2% hold от картата")
                          : t("credit_overlay.release_locked_hint", "Не можете да освободите, докато водите")}
                      >
                        <X size={11} />
                        {busy[h.authorization_id] ? t("common.processing", "Обработва…") : t("credit_overlay.release", "Освободи")}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
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
    </div>,
    document.body,
  );
}
