import React, { useEffect, useState, useCallback } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Wallet, ExternalLink, Plus, X, Trophy, Clock } from "lucide-react";
import { api, formatEUR } from "../lib/apiClient";
import { formatError, useAuth } from "../lib/auth";
import { auctionUrl } from "../lib/auctionUrl";

/**
 * /my-bids — single-page overview of every auction the signed-in user
 * currently has a preauthorization on, plus per-row actions.
 *
 * Data source: GET /api/stripe/authorizations/my-credits. The endpoint
 * already rolls up available/limit/hold per auction and is the same
 * data feeding the profile-menu wallet counter.
 *
 * Actions per row:
 *   • Наддай повече → deep-link into the auction's bid modal
 *   • Виж търга      → navigate to the auction page
 *   • Освободи кредит → POST /authorizations/{id}/release (server-side
 *     gate: cannot release while user is high bidder on LIVE auction)
 */
export default function MyBidsPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [releasing, setReleasing] = useState({}); // {auth_id: true}
  const [toast, setToast] = useState("");

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

  useEffect(() => { if (user) load(); else setLoading(false); }, [user, load]);

  useEffect(() => {
    if (!toast) return;
    const t2 = setTimeout(() => setToast(""), 3000);
    return () => clearTimeout(t2);
  }, [toast]);

  const release = async (hold) => {
    if (hold.is_leading && hold.auction_status === "live") {
      if (!window.confirm(t("my_bids.release_warning", "Вие сте текущ лидер — сървърът ще откаже освобождаването. Продължаване?"))) return;
    } else {
      if (!window.confirm(t("my_bids.release_confirm", "Освобождаване на авторизация за {{title}}? Това ще отмени наддавателния Ви лимит за този търг.", { title: hold.auction_title }))) return;
    }
    setReleasing((r) => ({ ...r, [hold.authorization_id]: true }));
    try {
      await api.post(`/stripe/authorizations/${hold.authorization_id}/release`);
      setToast(t("my_bids.released_ok", "Авторизацията е освободена."));
      load();
    } catch (e) {
      setErr(formatError(e));
    } finally {
      setReleasing((r) => ({ ...r, [hold.authorization_id]: false }));
    }
  };

  if (!user) {
    return (
      <div className="max-w-[1200px] mx-auto px-4 sm:px-6 lg:px-10 py-20" data-testid="my-bids-anon">
        <h1 className="font-serif text-3xl mb-4">{t("my_bids.title", "Моите наддавания")}</h1>
        <p className="text-[hsl(var(--ink-muted))] mb-6">{t("my_bids.login_required", "Трябва да влезете, за да видите наддаванията си.")}</p>
        <Link to="/login" className="btn btn-primary">{t("nav.login")}</Link>
      </div>
    );
  }

  return (
    <div className="max-w-[1200px] mx-auto px-4 sm:px-6 lg:px-10 py-12" data-testid="my-bids-page">
      <div className="flex items-start justify-between gap-4 flex-wrap mb-8">
        <div>
          <h1 className="font-serif text-3xl lg:text-4xl tracking-tight">{t("my_bids.title", "Моите наддавания")}</h1>
          <p className="text-sm text-[hsl(var(--ink-muted))] mt-1 max-w-xl">
            {t("my_bids.subtitle", "Преглед на всички активни авторизации. Можете да наддавате повече, да следите търг или да освободите кредит.")}
          </p>
        </div>
        {summary && summary.count > 0 && (
          <div className="rounded-card border border-[hsl(var(--line))] p-4 bg-[hsl(var(--surface))] flex items-center gap-3" data-testid="my-bids-summary">
            <Wallet size={18} className="text-[hsl(var(--accent))]" />
            <div>
              <div className="overline text-[hsl(var(--ink-muted))]">{t("my_bids.total_available", "Общо налично")}</div>
              <div className="text-xl font-serif tabular-nums" data-testid="my-bids-total-available">
                {formatEUR(summary.total_available_eur)}
              </div>
              <div className="text-[11px] text-[hsl(var(--ink-muted))] mt-0.5">
                {t("my_bids.of_limit", "от лимит {{limit}}", { limit: formatEUR(summary.total_limit_eur) })}
              </div>
            </div>
          </div>
        )}
      </div>

      {err && <div className="rounded-card border border-red-300 bg-red-50 text-red-800 px-4 py-3 mb-6 text-sm" data-testid="my-bids-error">{err}</div>}
      {toast && <div className="fixed bottom-6 right-6 rounded-card border border-emerald-400 bg-emerald-50 text-emerald-800 px-4 py-3 text-sm shadow-lg z-50" data-testid="my-bids-toast">{toast}</div>}

      {loading ? (
        <div className="text-[hsl(var(--ink-muted))]">{t("common.loading", "Зарежда…")}</div>
      ) : !summary || summary.count === 0 ? (
        <div className="text-center py-20 border border-dashed border-[hsl(var(--line))] rounded-card" data-testid="my-bids-empty">
          <Wallet size={32} className="mx-auto text-[hsl(var(--ink-muted))] mb-4" />
          <h2 className="font-serif text-xl mb-2">{t("my_bids.empty_title", "Нямате активни наддавания")}</h2>
          <p className="text-[hsl(var(--ink-muted))] mb-6">{t("my_bids.empty_body", "Щом авторизирате карта за търг, ще се появи тук.")}</p>
          <Link to="/auctions" className="btn btn-primary" data-testid="my-bids-browse-auctions">
            {t("my_bids.browse_auctions", "Разгледай търгове")}
          </Link>
        </div>
      ) : (
        <div className="space-y-4">
          {summary.holds.map((h) => {
            const auctionLink = auctionUrl({ id: h.auction_id, slug: h.auction_slug, title: h.auction_title });
            const ended = h.auction_status && h.auction_status !== "live" && h.auction_status !== "scheduled";
            const canReleaseFreely = !h.is_leading || ended;
            return (
              <div key={h.authorization_id} className="rounded-card border border-[hsl(var(--line))] p-4 flex gap-4 items-center flex-wrap" data-testid={`my-bids-row-${h.auction_id}`}>
                {h.auction_thumb && (
                  <Link to={auctionLink} className="shrink-0">
                    <img src={h.auction_thumb} alt="" className="w-24 h-16 object-cover rounded" loading="lazy" />
                  </Link>
                )}
                <div className="flex-1 min-w-[200px]">
                  <Link to={auctionLink} className="font-serif text-lg hover:text-[hsl(var(--accent))] line-clamp-1" data-testid={`my-bids-title-${h.auction_id}`}>
                    {h.auction_title}
                  </Link>
                  <div className="flex items-center gap-3 mt-1 text-xs">
                    {h.is_leading ? (
                      <span className="inline-flex items-center gap-1 text-emerald-700 font-semibold" data-testid={`my-bids-leading-${h.auction_id}`}>
                        <Trophy size={11} /> {t("my_bids.leading", "Водите")}
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-amber-700" data-testid={`my-bids-outbid-${h.auction_id}`}>
                        <Clock size={11} /> {t("my_bids.outbid", "Надминат")}
                      </span>
                    )}
                    <span className="text-[hsl(var(--ink-muted))]">
                      {t("my_bids.current_bid", "Текуща: {{amt}}", { amt: formatEUR(h.current_bid_eur) })}
                    </span>
                  </div>
                </div>

                {/* Credit figures */}
                <div className="text-right shrink-0">
                  <div className="overline text-[hsl(var(--ink-muted))]">{t("my_bids.available", "Налично")}</div>
                  <div className="font-mono text-sm tabular-nums" data-testid={`my-bids-available-${h.auction_id}`}>
                    {formatEUR(h.available_eur)}
                    <span className="text-[hsl(var(--ink-muted))]"> / {formatEUR(h.bidding_limit_eur)}</span>
                  </div>
                </div>

                {/* Actions */}
                <div className="flex items-center gap-2 flex-wrap">
                  <Link
                    to={`${auctionLink}?bid=1`}
                    className="btn btn-primary !py-1.5 !px-3 text-xs inline-flex items-center gap-1"
                    data-testid={`my-bids-bid-more-${h.auction_id}`}
                  >
                    <Plus size={12} /> {t("my_bids.bid_more", "Наддай повече")}
                  </Link>
                  <Link
                    to={auctionLink}
                    className="btn btn-secondary !py-1.5 !px-3 text-xs inline-flex items-center gap-1"
                    data-testid={`my-bids-view-${h.auction_id}`}
                  >
                    <ExternalLink size={12} /> {t("my_bids.view", "Виж търга")}
                  </Link>
                  <button
                    type="button"
                    onClick={() => release(h)}
                    disabled={releasing[h.authorization_id]}
                    className={`btn !py-1.5 !px-3 text-xs inline-flex items-center gap-1 ${canReleaseFreely ? "btn-secondary" : "btn-secondary opacity-60"}`}
                    data-testid={`my-bids-release-${h.auction_id}`}
                    title={canReleaseFreely
                      ? t("my_bids.release_hint", "Освобождава 2% hold от картата")
                      : t("my_bids.release_locked_hint", "Не можете да освободите, докато водите")}
                  >
                    <X size={12} /> {releasing[h.authorization_id] ? t("common.processing", "Обработва…") : t("my_bids.release", "Освободи кредит")}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
