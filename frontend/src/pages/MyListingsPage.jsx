import React, { useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { Plus, Clock, CheckCircle2, XCircle, Gavel, Archive, AlertCircle, Edit3, Trash2, Gift, HandCoins, Star, FileEdit, Images } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useAuth, formatError } from "../lib/auth";
import { api, formatEUR, timeLeft, formatTimeLeft } from "../lib/apiClient";
import { grossEUR } from "../lib/vat";
import SellerRequestModal from "../components/SellerRequestModal";
import { auctionUrl } from "../lib/auctionUrl";

/** i18n-aware status metadata: labels come from locales, icons+colors stay static */
const STATUS_ICON = {
  pending: { icon: Clock, cls: "text-[hsl(var(--ink-muted))] border-[hsl(var(--line))]" },
  live: { icon: Gavel, cls: "text-[hsl(var(--accent))] border-[hsl(var(--accent))]/40 bg-[hsl(var(--accent-soft))]" },
  sold: { icon: CheckCircle2, cls: "text-[hsl(var(--success))] border-[hsl(var(--success))]/40" },
  ended: { icon: Archive, cls: "text-[hsl(var(--ink-muted))] border-[hsl(var(--line))]" },
  rejected: { icon: XCircle, cls: "text-[hsl(var(--danger))] border-[hsl(var(--danger))]/40" },
  withdrawn: { icon: Archive, cls: "text-[hsl(var(--ink-muted))] border-[hsl(var(--line))]" },
  reserve_not_met: { icon: HandCoins, cls: "text-[hsl(var(--danger))] border-[hsl(var(--danger))]/40" },
};

export default function MyListingsPage() {
  const { t } = useTranslation();
  const { user, loading } = useAuth();
  const [items, setItems] = useState(null);
  const [editing, setEditing] = useState(null);
  const [editForm, setEditForm] = useState({});
  const [counterFor, setCounterFor] = useState(null);
  const [counterPrice, setCounterPrice] = useState("");
  const [err, setErr] = useState("");
  const [requestsByAuction, setRequestsByAuction] = useState({});
  const [modal, setModal] = useState(null); // { auction, mode }

  const load = async () => {
    try {
      const { data } = await api.get("/me/listings");
      setItems(data);
      // Parallel: pending seller requests for visual badges
      try {
        const { data: reqs } = await api.get("/me/seller-requests", { params: { status: "pending" } });
        const map = {};
        for (const r of reqs || []) {
          map[r.auction_id] = map[r.auction_id] || {};
          map[r.auction_id][r.type] = r;
        }
        setRequestsByAuction(map);
      } catch { /* non-blocking */ }
    }
    catch (e) { setItems([]); }
  };

  useEffect(() => { if (user) load(); }, [user]);

  // ─── Promotion-payment return handler ────────────────────────────────
  // After Stripe Checkout the seller returns to /my-listings with either
  // `?promote_session=<id>` (success) or `?promote_cancelled=1`. We call
  // /promote/finalize to activate the `featured` flag — the backend is
  // idempotent so a refresh is safe. `payment_status` may still be
  // `unpaid` for ~1s while Stripe's webhook catches up; retry on 402.
  useEffect(() => {
    if (!user) return;
    const params = new URLSearchParams(window.location.search);
    const promoteSid = params.get("promote_session");
    const promoteCancelled = params.get("promote_cancelled");
    if (promoteCancelled) {
      setErr(t("seller.promote_cancelled", "Плащането за промотиране бе отказано."));
      params.delete("promote_cancelled");
      window.history.replaceState({}, "", `${window.location.pathname}${params.toString() ? "?" + params : ""}`);
      return;
    }
    if (!promoteSid || !items) return;
    let cancel = false;
    (async () => {
      // Need the auction id: the session doesn't carry it on the client,
      // so we iterate over pending listings and ask the backend which one
      // matches via the session metadata. Simpler: scan seller listings
      // and try each until one succeeds — realistically only 1-3 retries.
      for (const a of items || []) {
        if (cancel) return;
        if (a.featured) continue;
        for (let i = 0; i < 8 && !cancel; i++) {
          try {
            await api.post(`/auctions/${a.id}/promote/finalize`, { session_id: promoteSid });
            await load();
            params.delete("promote_session");
            window.history.replaceState({}, "", `${window.location.pathname}${params.toString() ? "?" + params : ""}`);
            return;
          } catch (e) {
            const status = e?.response?.status;
            if (status === 400 || status === 403) break; // wrong auction, try next
            if (status === 402) { await new Promise((r) => setTimeout(r, 2000)); continue; }
            break;
          }
        }
      }
      params.delete("promote_session");
      window.history.replaceState({}, "", `${window.location.pathname}${params.toString() ? "?" + params : ""}`);
    })();
    return () => { cancel = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, items?.length]);

  if (loading) return <div className="py-24 text-center">{t("watchlist.loading")}</div>;
  if (!user) return <Navigate to="/login?next=/my-listings" replace />;

  const startEdit = (a) => {
    setEditing(a.id);
    setEditForm({
      title: a.title,
      description: a.description,
      starting_bid_eur: a.starting_bid_eur,
      reserve_eur: a.reserve_eur || "",
      buy_now_eur: a.buy_now_eur || "",
    });
  };
  const saveEdit = async (id) => {
    setErr("");
    try {
      const body = { ...editForm };
      body.starting_bid_eur = Number(body.starting_bid_eur);
      body.reserve_eur = body.reserve_eur === "" ? null : Number(body.reserve_eur);
      await api.patch(`/auctions/${id}`, body);
      setEditing(null);
      load();
    } catch (e) { setErr(formatError(e)); }
  };
  const withdraw = async (id) => {
    if (!window.confirm("Оттеглете ли тази обява?")) return;
    setErr("");
    try { await api.delete(`/auctions/${id}`); load(); }
    catch (e) { setErr(formatError(e)); }
  };
  const acceptHighBid = async (id) => {
    if (!window.confirm("Приемате ли водещото наддаване?")) return;
    setErr("");
    try { await api.post(`/auctions/${id}/accept-high-bid`); load(); }
    catch (e) { setErr(formatError(e)); }
  };
  const sendCounter = async (id) => {
    if (!counterPrice || Number(counterPrice) <= 0) { setErr("Невалидна цена"); return; }
    setErr("");
    try {
      await api.post(`/auctions/${id}/counter-offer`, { price_eur: Number(counterPrice) });
      setCounterFor(null); setCounterPrice("");
      load();
    } catch (e) { setErr(formatError(e)); }
  };

  return (
    <main data-testid="my-listings-page">
      <div className="max-w-[1200px] mx-auto px-4 sm:px-6 lg:px-10 py-16">
        <div className="flex items-end justify-between gap-4 flex-wrap">
          <div>
            <div className="overline text-[hsl(var(--accent))]">{t("my_listings.overline")}</div>
            <h1 className="font-serif text-4xl lg:text-5xl tracking-tight mt-3">{t("my_listings.title")}</h1>
            <p className="mt-3 text-sm text-[hsl(var(--ink-muted))]">{t("my_listings.subtitle")}</p>
          </div>
          <Link to="/sell" className="btn btn-primary flex items-center gap-2" data-testid="new-listing-btn">
            <Plus size={14} /> {t("my_listings.new_listing")}
          </Link>
        </div>

        {err && <p className="mt-4 text-sm text-[hsl(var(--danger))]" data-testid="listings-error">{err}</p>}

        {items === null ? (
          <div className="py-24 text-center text-[hsl(var(--ink-muted))]">{t("watchlist.loading")}</div>
        ) : items.length === 0 ? (
          <div className="mt-12 py-24 text-center rounded-card border border-[hsl(var(--line))]" data-testid="my-listings-empty">
            <AlertCircle size={32} className="mx-auto text-[hsl(var(--ink-muted))]" />
            <p className="mt-4 font-serif text-2xl">{t("my_listings.empty_title")}</p>
            <p className="mt-2 text-sm text-[hsl(var(--ink-muted))]">{t("my_listings.empty_hint")}</p>
            <Link to="/sell" className="btn btn-primary mt-6 inline-flex">{t("my_listings.start_sell")}</Link>
          </div>
        ) : (
          <div className="mt-10 space-y-5" data-testid="my-listings-list">
            {items.map((a) => {
              const icon = STATUS_ICON[a.status] || STATUS_ICON.pending;
              const Icon = icon.icon;
              const statusLabel = t(`my_listings.status.${a.status}`, t(`my_listings.status.pending`));
              const tl = a.status === "live" ? timeLeft(a.ends_at) : null;
              const canEdit = a.status === "pending" || a.status === "rejected" || (a.status === "live" && (a.bid_count || 0) === 0);
              const canWithdraw = ["pending", "rejected", "ended", "reserve_not_met"].includes(a.status) || (a.status === "live" && (a.bid_count || 0) === 0);
              const isRNM = a.status === "reserve_not_met";
              const counter = a.counter_status;

              return (
                <div key={a.id} className="rounded-card border border-[hsl(var(--line))] overflow-hidden bg-white" data-testid={`listing-${a.id}`}>
                  <div className="grid grid-cols-1 md:grid-cols-[180px_1fr_auto] gap-0">
                    <div className="aspect-[4/3] md:aspect-auto md:min-h-[160px] bg-[hsl(var(--surface))]">
                      {a.images?.[0] ? <img src={a.thumbnails?.[0] || a.images[0]} alt={a.title} className="w-full h-full object-cover" loading="lazy" /> : <div className="w-full h-full flex items-center justify-center text-[hsl(var(--ink-muted))] text-xs">Без снимка</div>}
                    </div>
                    <div className="p-5">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className={`pill ${icon.cls}`} data-testid={`status-${a.id}`}><Icon size={11} /> {statusLabel}</span>
                        {a.has_reserve && (a.reserve_met
                          ? <span className="pill pill-live">{t("auction.reserve_met", "Резервът е достигнат")}</span>
                          : <span className="pill">{t("auction.with_reserve_amount", "С резерв")} · €{Math.round(a.reserve_eur || 0).toLocaleString("bg-BG")}</span>)}
                        {a.has_reserve === false && <span className="pill no-reserve-gradient">{t("auction.no_reserve_badge", "Без резерв")}</span>}
                        {counter === "pending" && <span className="pill pill-ending">{t("auction.counter_pending", "Чака отговор")}</span>}
                        {counter === "declined" && <span className="pill pill-sold">{t("auction.counter_declined", "Отказан контраоферта")}</span>}
                      </div>
                      {editing === a.id ? (
                        <div className="mt-4 space-y-3">
                          <input value={editForm.title || ""} onChange={(e) => setEditForm({...editForm, title: e.target.value})} className="w-full border border-[hsl(var(--line))] h-10 px-3 text-sm" placeholder="Заглавие" data-testid={`edit-title-${a.id}`} />
                          <textarea value={editForm.description || ""} onChange={(e) => setEditForm({...editForm, description: e.target.value})} rows={3} className="w-full border border-[hsl(var(--line))] p-3 text-sm" placeholder="Описание" />
                          <div className="grid grid-cols-2 gap-3">
                            <input type="number" value={editForm.starting_bid_eur || ""} onChange={(e) => setEditForm({...editForm, starting_bid_eur: e.target.value})} className="w-full border border-[hsl(var(--line))] h-10 px-3 text-sm" placeholder="Начална €" />
                            <input type="number" value={editForm.reserve_eur || ""} onChange={(e) => setEditForm({...editForm, reserve_eur: e.target.value})} className="w-full border border-[hsl(var(--line))] h-10 px-3 text-sm" placeholder="Резерв € (опц.)" />
                          </div>
                          <div className="flex gap-2 justify-end">
                            <button onClick={() => setEditing(null)} className="btn btn-secondary !py-2 !px-4">Отказ</button>
                            <button onClick={() => saveEdit(a.id)} className="btn btn-primary !py-2 !px-4" data-testid={`save-edit-${a.id}`}>Запази</button>
                          </div>
                        </div>
                      ) : (
                        <>
                          <h3 className="font-serif text-xl mt-3">{a.title}</h3>
                          <div className="mt-2 text-sm text-[hsl(var(--ink-muted))]">{a.make} · {a.year} г. · {a.city}</div>
                          {a.status === "rejected" && a.rejected_reason && (
                            <div className="mt-3 text-xs rounded-card bg-[hsl(0_74%_97%)] border border-[hsl(var(--danger))]/30 p-3 text-[hsl(var(--danger))]" data-testid={`reject-reason-${a.id}`}>
                              <strong>{t("seller.note_for_mod").split(" ")[0]}:</strong> {a.rejected_reason}
                            </div>
                          )}
                          {isRNM && counter !== "pending" && counter !== "accepted" && (
                            <div className="mt-4 p-4 rounded-card bg-[hsl(var(--surface))] border border-[hsl(var(--line))]">
                              <div className="overline text-[hsl(var(--accent))]">{t("auction.auction_ended_below_reserve")}</div>
                              <p className="mt-2 text-sm">
                                {t("auction.auction_ended_below_reserve_hint", {
                                  bid: formatEUR(grossEUR(a.current_bid_eur, a)),
                                  reserve: formatEUR(grossEUR(a.reserve_eur || 0, a)),
                                })}
                              </p>
                              <div className="mt-3 flex flex-wrap gap-2">
                                <button onClick={() => acceptHighBid(a.id)} className="btn btn-accent !py-2 !px-4 text-xs flex items-center gap-2" data-testid={`accept-high-${a.id}`}>
                                  <CheckCircle2 size={13} /> {t("auction.accept_high_bid", { amount: formatEUR(grossEUR(a.current_bid_eur, a)) })}
                                </button>
                                <button onClick={() => setCounterFor(a.id)} className="btn btn-primary !py-2 !px-4 text-xs flex items-center gap-2" data-testid={`counter-${a.id}`}>
                                  <Gift size={13} /> {t("auction.counter_offer_cta")}
                                </button>
                              </div>
                              {counterFor === a.id && (
                                <div className="mt-4 flex gap-2">
                                  <input type="number" value={counterPrice} onChange={(e) => setCounterPrice(e.target.value)} placeholder={t("auction.counter_placeholder")} className="flex-1 border border-[hsl(var(--line))] h-10 px-3 text-sm" data-testid={`counter-price-${a.id}`} />
                                  <button onClick={() => sendCounter(a.id)} className="btn btn-accent !py-2 !px-4 text-xs" data-testid={`send-counter-${a.id}`}>{t("auction.send_counter")}</button>
                                  <button onClick={() => { setCounterFor(null); setCounterPrice(""); }} className="btn btn-secondary !py-2 !px-4 text-xs">{t("forms.cancel")}</button>
                                </div>
                              )}
                            </div>
                          )}
                          {counter === "pending" && (
                            <p className="mt-3 text-xs text-[hsl(var(--ink-muted))]">{t("auction.pending_counter")} · {formatEUR(grossEUR(a.counter_offer_eur, a))}</p>
                          )}

                          <div className="mt-4 flex gap-2 flex-wrap">
                            {canEdit && <button onClick={() => startEdit(a)} className="btn btn-secondary !py-2 !px-3 text-xs flex items-center gap-1.5" data-testid={`edit-${a.id}`}><Edit3 size={12} /> {t("my_listings.edit")}</button>}
                            {canWithdraw && <button onClick={() => withdraw(a.id)} className="btn btn-secondary !py-2 !px-3 text-xs flex items-center gap-1.5" data-testid={`withdraw-${a.id}`}><Trash2 size={12} /> {t("my_listings.withdraw")}</button>}
                            {/* Self-service seller requests (available while pending / live / paused) */}
                            {["pending", "live", "paused"].includes(a.status) && (
                              <>
                                <button
                                  onClick={() => setModal({ auction: a, mode: "reorder" })}
                                  className="btn btn-secondary !py-2 !px-3 text-xs flex items-center gap-1.5"
                                  data-testid={`reorder-photos-${a.id}`}
                                  disabled={(a.images || []).length < 2}
                                  title={(a.images || []).length < 2 ? t("seller.reorder_description") : t("seller.reorder_photos")}
                                >
                                  <Images size={12} /> {t("seller.reorder_photos")}
                                </button>
                                <button
                                  onClick={() => setModal({ auction: a, mode: "text" })}
                                  className="btn btn-secondary !py-2 !px-3 text-xs flex items-center gap-1.5"
                                  data-testid={`request-text-${a.id}`}
                                  disabled={!!requestsByAuction[a.id]?.text_change}
                                  title={requestsByAuction[a.id]?.text_change ? t("seller.pending_request") : t("seller.text_change_description")}
                                >
                                  <FileEdit size={12} /> {requestsByAuction[a.id]?.text_change ? t("seller.pending_request") : t("seller.request_text_change")}
                                </button>
                                {!a.featured && (
                                  <button
                                    onClick={async () => {
                                      if (!window.confirm(t("seller.promote_confirm", "Промотирайте обявата за €30? Плащането е еднократно."))) return;
                                      try {
                                        const { data } = await api.post(`/auctions/${a.id}/promote/checkout`, {
                                          origin: window.location.origin,
                                        });
                                        if (data?.url) window.location.assign(data.url);
                                      } catch (e) {
                                        setErr(formatError(e));
                                      }
                                    }}
                                    className="btn btn-secondary !py-2 !px-3 text-xs flex items-center gap-1.5 !border-amber-400 !text-amber-700"
                                    data-testid={`promote-paid-${a.id}`}
                                    title={t("seller.promote_description", "Промотирайте обявата си за €30")}
                                  >
                                    <Star size={12} /> {t("seller.promote_paid", "Промотирай — €30")}
                                  </button>
                                )}
                                {a.featured && (
                                  <span className="pill text-xs text-amber-700 border-amber-300 bg-amber-50" data-testid={`featured-badge-${a.id}`}>
                                    <Star size={11} /> {t("auction.featured_badge")}
                                  </span>
                                )}
                              </>
                            )}
                          </div>
                        </>
                      )}
                    </div>
                    <div className="p-5 md:border-l border-[hsl(var(--line))] flex flex-col justify-center items-start md:items-end gap-2 min-w-[200px]">
                      {a.status === "live" && (<>
                        <div className="overline text-[hsl(var(--ink-muted))]">Текуща</div>
                        <div className="font-serif text-2xl">{formatEUR(grossEUR(a.current_bid_eur, a))}</div>
                        <div className="text-xs text-[hsl(var(--ink-muted))]">{a.bid_count || 0} {t("time.bids_short")} · {tl ? formatTimeLeft(tl, t) : ""}</div>
                      </>)}
                      {a.status === "sold" && (<>
                        <div className="overline text-[hsl(var(--ink-muted))]">Продаден за</div>
                        <div className="font-serif text-2xl">{formatEUR(grossEUR(a.current_bid_eur, a))}</div>
                      </>)}
                      {(a.status === "pending" || a.status === "rejected" || a.status === "withdrawn") && (<>
                        <div className="overline text-[hsl(var(--ink-muted))]">Начална</div>
                        <div className="font-serif text-2xl">{formatEUR(grossEUR(a.starting_bid_eur, a))}</div>
                      </>)}
                      {isRNM && (<>
                        <div className="overline text-[hsl(var(--ink-muted))]">Водеща оферта</div>
                        <div className="font-serif text-2xl">{formatEUR(grossEUR(a.current_bid_eur, a))}</div>
                      </>)}
                      {(a.status === "live" || a.status === "sold" || isRNM) && <Link to={auctionUrl(a)} className="btn btn-secondary !py-2 !px-4 mt-1">Виж обявата</Link>}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {modal && (
        <SellerRequestModal
          auction={modal.auction}
          mode={modal.mode}
          onClose={() => setModal(null)}
          onDone={() => load()}
        />
      )}
    </main>
  );
}
