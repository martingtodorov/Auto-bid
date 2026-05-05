import React, { useEffect, useState, useCallback, useMemo, useRef } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Wallet, ExternalLink, Plus, X, Clock, Gavel } from "lucide-react";
import { api, formatEUR } from "../lib/apiClient";
import { formatError, useAuth } from "../lib/auth";
import { auctionUrl } from "../lib/auctionUrl";
import { minNextBid } from "../lib/bidUtils";
import TopUpCreditModal from "../components/TopUpCreditModal";

const API_BASE = process.env.REACT_APP_BACKEND_URL;

/**
 * /my-bids — детайлен преглед на акаунтния наддавателен кредит.
 *
 * Data: GET /api/stripe/authorizations/my-credits → връща
 *   • holds[]        — активни Stripe авторизации (могат да се освободят)
 *   • commitments[]  — текущи lead-нати търгове (заключен кредит)
 *
 * Кредитът е универсален и НЕ е свързан с конкретен търг — потребителят
 * зарежда X евро и ги харчи където поиска.
 */
export default function MyBidsPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [releasing, setReleasing] = useState({});
  const [toast, setToast] = useState("");
  const [showTopUp, setShowTopUp] = useState(false);
  const [bidding, setBidding] = useState({});  // { auction_id: bool }
  const wsRefs = useRef({});  // { auction_id: WebSocket }
  const reloadTimer = useRef(null);

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

  // Debounced reload — multiple WS events within 500ms collapse into one
  // network round-trip. Prevents thundering-herd when many bids land in
  // quick succession (sniping window).
  const debouncedReload = useCallback(() => {
    if (reloadTimer.current) clearTimeout(reloadTimer.current);
    reloadTimer.current = setTimeout(() => { load(); }, 500);
  }, [load]);

  useEffect(() => { if (user) load(); else setLoading(false); }, [user, load]);

  // Auto-open top-up modal if URL contains ?topup=1 (deep-link from CTAs)
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("topup") === "1") {
      setShowTopUp(true);
      params.delete("topup");
      window.history.replaceState({}, "", `${window.location.pathname}${params.toString() ? "?" + params : ""}`);
    }
    if (params.get("stripe_session_id")) {
      // User is back from Stripe — refresh credits + nav counter.
      window.dispatchEvent(new Event("credits-updated"));
      params.delete("stripe_session_id");
      window.history.replaceState({}, "", `${window.location.pathname}${params.toString() ? "?" + params : ""}`);
    }
  }, []);

  useEffect(() => {
    if (!toast) return;
    const t2 = setTimeout(() => setToast(""), 3000);
    return () => clearTimeout(t2);
  }, [toast]);

  const release = async (hold) => {
    if (!window.confirm(t("my_bids.release_confirm_v2",
      "Освободи {{lim}} от наддавателния кредит?", { lim: formatEUR(hold.bidding_limit_eur) }))) return;
    setReleasing((r) => ({ ...r, [hold.authorization_id]: true }));
    try {
      await api.post(`/stripe/authorizations/${hold.authorization_id}/release`);
      setToast(t("my_bids.released_ok", "Авторизацията е освободена."));
      window.dispatchEvent(new Event("credits-updated"));
      load();
    } catch (e) {
      setErr(formatError(e));
    } finally {
      setReleasing((r) => ({ ...r, [hold.authorization_id]: false }));
    }
  };

  // Quick re-bid — fire from a card row directly. Asks for confirmation
  // (window.confirm) showing the next minimum bid. Backend authoritative
  // on min_next, so we re-fetch /next-bid to get the exact server number
  // (avoids stale state if WS event hasn't arrived yet).
  const quickBid = async (auctionId, auctionTitle, currentBid) => {
    setBidding((b) => ({ ...b, [auctionId]: true }));
    try {
      // 1. Pull authoritative next-bid from server.
      let next;
      try {
        const r = await api.get(`/auctions/${auctionId}/next-bid`);
        next = r.data;
      } catch (e) {
        next = { min_next_eur: minNextBid(currentBid) };
      }
      const amount = Number(next?.min_next_eur || minNextBid(currentBid));
      // 2. Confirm with the user.
      const ok = window.confirm(
        t("my_bids.quick_bid_confirm",
          "Наддай {{amt}} на {{title}}?",
          { amt: formatEUR(amount), title: auctionTitle }),
      );
      if (!ok) return;
      // 3. Submit. Backend re-validates min on its side under FOR UPDATE.
      await api.post(`/auctions/${auctionId}/bids`, { amount_eur: amount });
      setToast(t("my_bids.bid_placed", "Наддаването е изпратено: {{amt}}", { amt: formatEUR(amount) }));
      window.dispatchEvent(new Event("credits-updated"));
      // WS event will reload too, but force one in case WS is slow/down.
      load();
    } catch (e) {
      setErr(formatError(e));
    } finally {
      setBidding((b) => ({ ...b, [auctionId]: false }));
    }
  };

  // Subscribe to WebSocket events for every auction the user has stake
  // in (commitments + outbid). On any `bid` event we debounced-reload
  // /my-credits. This replaces a polling timer with push-based updates.
  const auctionIds = useMemo(() => {
    if (!summary) return [];
    const ids = new Set();
    (summary.commitments || []).forEach((c) => c.auction_id && ids.add(c.auction_id));
    (summary.outbid_bids || []).forEach((c) => c.auction_id && ids.add(c.auction_id));
    return Array.from(ids);
  }, [summary]);

  useEffect(() => {
    if (!user || !auctionIds.length || !API_BASE) return;
    const wsUrl = API_BASE.replace(/^http/, "ws");
    const opened = {};
    auctionIds.forEach((id) => {
      try {
        const ws = new WebSocket(`${wsUrl}/api/ws/auctions/${id}`);
        ws.onmessage = (ev) => {
          try {
            const msg = JSON.parse(ev.data);
            if (msg.type === "bid") debouncedReload();
          } catch (e) {}
        };
        ws.onerror = () => {};
        opened[id] = ws;
      } catch (e) {}
    });
    wsRefs.current = opened;
    return () => {
      Object.values(opened).forEach((w) => { try { w.close(); } catch (e) {} });
      wsRefs.current = {};
      if (reloadTimer.current) { clearTimeout(reloadTimer.current); reloadTimer.current = null; }
    };
  }, [auctionIds, user, debouncedReload]);

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
      <h1 className="font-serif text-3xl mb-8">{t("my_bids.title", "Моите наддавания")}</h1>

      {summary && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8" data-testid="my-bids-totals">
          <div className="rounded-card border border-[hsl(var(--line))] bg-[hsl(var(--surface))] p-5">
            <div className="overline text-[hsl(var(--ink-muted))] mb-1.5">{t("my_bids.available", "Налично")}</div>
            <div className="font-serif text-3xl tabular-nums" data-testid="my-bids-available">
              {formatEUR(summary.total_available_eur)}
            </div>
            <div className="text-xs text-[hsl(var(--ink-muted))] mt-1">
              {t("my_bids.available_hint", "за наддаване сега")}
            </div>
          </div>
          <div className="rounded-card border border-[hsl(var(--line))] p-5">
            <div className="overline text-[hsl(var(--ink-muted))] mb-1.5">{t("my_bids.limit", "Авторизирано")}</div>
            <div className="font-serif text-3xl tabular-nums">{formatEUR(summary.total_limit_eur)}</div>
            <div className="text-xs text-[hsl(var(--ink-muted))] mt-1">
              {summary.count} {t("my_bids.holds_count", "активни авторизации")}
            </div>
          </div>
          <div className="rounded-card border border-[hsl(var(--line))] p-5">
            <div className="overline text-[hsl(var(--ink-muted))] mb-1.5">{t("my_bids.committed", "Ангажирано")}</div>
            <div className="font-serif text-3xl tabular-nums">{formatEUR(summary.total_committed_eur || 0)}</div>
            <div className="text-xs text-[hsl(var(--ink-muted))] mt-1">
              {(summary.commitments || []).length} {t("my_bids.commit_count", "лидерски бида")}
            </div>
          </div>
        </div>
      )}

      <div className="mb-8">
        <button
          type="button"
          onClick={() => setShowTopUp(true)}
          className="btn btn-primary inline-flex items-center gap-2"
          data-testid="my-bids-topup"
        >
          <Plus size={14} /> {t("my_bids.topup_cta", "Зареди още кредит")}
        </button>
      </div>

      {err && (
        <div className="rounded-card border border-red-300 bg-red-50 text-red-800 px-4 py-3 mb-6" data-testid="my-bids-error">
          {err}
        </div>
      )}
      {toast && (
        <div className="rounded-card border border-green-300 bg-green-50 text-green-800 px-4 py-3 mb-6" data-testid="my-bids-toast">
          {toast}
        </div>
      )}

      {/* COMMITMENTS — auctions where the user currently leads. These
          can be navigated to but cannot be released directly here;
          the user must wait to be outbid or the auction to end. */}
      {summary && summary.commitments && summary.commitments.length > 0 && (
        <section className="mb-10" data-testid="my-bids-commitments">
          <h2 className="font-serif text-2xl mb-4">{t("my_bids.committed_title", "Активни наддавания")}</h2>
          <div className="space-y-3">
            {summary.commitments.map((c) => {
              const next = minNextBid(c.current_bid_eur);
              const busy = !!bidding[c.auction_id];
              return (
              <div
                key={c.auction_id}
                className="rounded-card border border-emerald-300 bg-emerald-50/40"
                data-testid={`my-bids-commit-${c.auction_id}`}
              >
                <button
                  type="button"
                  onClick={() => navigate(auctionUrl({ id: c.auction_id, slug: c.auction_slug, title: c.auction_title }))}
                  className="w-full text-left flex items-center gap-4 p-4 hover:bg-emerald-50/70 rounded-card"
                >
                  {c.auction_thumb && (
                    <img src={c.auction_thumb} alt="" className="w-20 h-14 object-cover rounded shrink-0" loading="lazy" />
                  )}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold line-clamp-1">{c.auction_title}</span>
                      <span className="text-[10px] uppercase tracking-wide font-bold shrink-0 px-1.5 py-0.5 rounded bg-emerald-600 text-white">
                        {t("inbox.bid_leading", "Водите")}
                      </span>
                    </div>
                    <div className="text-xs text-[hsl(var(--ink-muted))] tabular-nums mt-0.5">
                      {formatEUR(c.current_bid_eur)} · <Clock size={10} className="inline" /> {new Date(c.ends_at).toLocaleString()}
                    </div>
                  </div>
                  <ExternalLink size={14} className="text-[hsl(var(--ink-muted))]" />
                </button>
                {/* Quick re-bid (up the leading bid by one step). Useful
                    when the user wants to deter snipers in the closing
                    minutes without leaving the My Bids page. */}
                <div className="px-4 pb-3 -mt-1">
                  <button
                    type="button"
                    onClick={() => quickBid(c.auction_id, c.auction_title, c.current_bid_eur)}
                    disabled={busy}
                    className="w-full btn btn-primary inline-flex items-center justify-center gap-1.5 !py-2 text-sm"
                    data-testid={`my-bids-quickbid-${c.auction_id}`}
                  >
                    <Gavel size={13} />
                    {busy
                      ? t("common.processing", "Обработва…")
                      : t("my_bids.quick_bid_cta", "Наддай {{amt}}", { amt: formatEUR(next) })}
                  </button>
                </div>
              </div>
              );
            })}
          </div>
        </section>
      )}

      {/* OUTBID — auctions where the user has bid but is currently
          outbid. Credit is freed automatically; user can re-enter
          without losing their authorization. */}
      {summary && summary.outbid_bids && summary.outbid_bids.length > 0 && (
        <section className="mb-10" data-testid="my-bids-outbid">
          <h2 className="font-serif text-2xl mb-4">{t("my_bids.outbid_title", "Надминати наддавания")}</h2>
          <div className="space-y-3">
            {summary.outbid_bids.map((c) => {
              const next = minNextBid(c.current_bid_eur);
              const busy = !!bidding[c.auction_id];
              return (
              <div
                key={c.auction_id}
                className="rounded-card border border-amber-300 bg-amber-50/40"
                data-testid={`my-bids-outbid-${c.auction_id}`}
              >
                <button
                  type="button"
                  onClick={() => navigate(auctionUrl({ id: c.auction_id, slug: c.auction_slug, title: c.auction_title }))}
                  className="w-full text-left flex items-center gap-4 p-4 hover:bg-amber-50/70 rounded-card"
                >
                  {c.auction_thumb && (
                    <img src={c.auction_thumb} alt="" className="w-20 h-14 object-cover rounded shrink-0" loading="lazy" />
                  )}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold line-clamp-1">{c.auction_title}</span>
                      <span className="text-[10px] uppercase tracking-wide font-bold shrink-0 px-1.5 py-0.5 rounded bg-amber-600 text-white">
                        {t("inbox.bid_outbid", "Надминати")}
                      </span>
                    </div>
                    <div className="text-xs text-[hsl(var(--ink-muted))] tabular-nums mt-0.5">
                      {t("inbox.current_vs_yours", "Текущ {{cur}} · ваш {{my}}", {
                        cur: formatEUR(c.current_bid_eur),
                        my: formatEUR(c.user_max_bid_eur),
                      })}
                      {" · "}<Clock size={10} className="inline" /> {new Date(c.ends_at).toLocaleString()}
                    </div>
                  </div>
                  <ExternalLink size={14} className="text-[hsl(var(--ink-muted))]" />
                </button>
                <div className="px-4 pb-3 -mt-1">
                  <button
                    type="button"
                    onClick={() => quickBid(c.auction_id, c.auction_title, c.current_bid_eur)}
                    disabled={busy}
                    className="w-full btn btn-primary inline-flex items-center justify-center gap-1.5 !py-2 text-sm"
                    data-testid={`my-bids-quickbid-${c.auction_id}`}
                  >
                    <Gavel size={13} />
                    {busy
                      ? t("common.processing", "Обработва…")
                      : t("my_bids.quick_bid_cta", "Наддай {{amt}}", { amt: formatEUR(next) })}
                  </button>
                </div>
              </div>
              );
            })}
          </div>
        </section>
      )}

      {/* HOLDS — Stripe authorizations on the card. Releasable subject
          to server-side guard (not over-committed). */}
      <section data-testid="my-bids-holds">
        <h2 className="font-serif text-2xl mb-4">{t("my_bids.holds_title", "Авторизации на картата")}</h2>
        {loading ? (
          <p className="text-[hsl(var(--ink-muted))]">{t("common.loading", "Зарежда…")}</p>
        ) : !summary || !summary.holds || summary.holds.length === 0 ? (
          <div className="rounded-card border border-dashed border-[hsl(var(--line))] p-8 text-center" data-testid="my-bids-empty">
            <Wallet size={32} className="mx-auto text-[hsl(var(--ink-muted))] mb-3" />
            <p className="text-sm text-[hsl(var(--ink-muted))]">
              {t("my_bids.empty_v2", "Все още нямате активни авторизации. Заредете кредит и започнете да наддавате.")}
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {summary.holds.map((h) => {
              const isPending = h.authorization_status === "pending";
              return (
                <div
                  key={h.authorization_id}
                  className="flex items-center justify-between gap-4 p-4 rounded-card border border-[hsl(var(--line))]"
                  data-testid={`my-bids-hold-${h.authorization_id}`}
                >
                  <div>
                    <div className="font-mono text-xl tabular-nums flex items-center gap-2">
                      {formatEUR(h.bidding_limit_eur)}
                      {isPending && (
                        <span className="text-[10px] uppercase tracking-wide bg-amber-100 text-amber-800 px-1.5 py-0.5 rounded">
                          {t("credit_overlay.pending", "Изчаква")}
                        </span>
                      )}
                    </div>
                    <div className="text-xs text-[hsl(var(--ink-muted))] mt-0.5">
                      {t("my_bids.hold_blocked", "Блокирано: {{h}}", { h: formatEUR(h.hold_eur) })}
                      {h.created_at && ` · ${new Date(h.created_at).toLocaleDateString()}`}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => release(h)}
                    disabled={releasing[h.authorization_id]}
                    className="btn btn-secondary !text-[hsl(var(--danger))] !border-[hsl(var(--danger))]/30 inline-flex items-center gap-1.5"
                    data-testid={`my-bids-release-${h.authorization_id}`}
                  >
                    <X size={13} />
                    {releasing[h.authorization_id]
                      ? t("common.processing", "Обработва…")
                      : t("my_bids.release", "Освободи")}
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </section>

      {showTopUp && (
        <TopUpCreditModal
          suggestedAmount={10000}
          onClose={() => setShowTopUp(false)}
        />
      )}
    </div>
  );
}
