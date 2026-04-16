import React, { useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { Plus, Clock, CheckCircle2, XCircle, Gavel, Archive, AlertCircle, Edit3, Trash2, Gift, HandCoins } from "lucide-react";
import { useAuth, formatError } from "../lib/auth";
import { api, formatEUR, timeLeft } from "../lib/apiClient";

const STATUS_META = {
  pending:          { label: "Очаква одобрение", icon: Clock,        cls: "text-[hsl(var(--ink-muted))] border-[hsl(var(--line))]" },
  live:             { label: "Активен търг",     icon: Gavel,        cls: "text-[hsl(var(--accent))] border-[hsl(var(--accent))]/40 bg-[hsl(var(--accent-soft))]" },
  sold:             { label: "Продаден",         icon: CheckCircle2, cls: "text-[hsl(var(--success))] border-[hsl(var(--success))]/40" },
  ended:            { label: "Приключил",        icon: Archive,      cls: "text-[hsl(var(--ink-muted))] border-[hsl(var(--line))]" },
  rejected:         { label: "Отказан",          icon: XCircle,      cls: "text-[hsl(var(--danger))] border-[hsl(var(--danger))]/40" },
  withdrawn:        { label: "Оттеглен",         icon: Archive,      cls: "text-[hsl(var(--ink-muted))] border-[hsl(var(--line))]" },
  reserve_not_met:  { label: "Резерв недостигнат", icon: HandCoins,  cls: "text-[hsl(var(--danger))] border-[hsl(var(--danger))]/40" },
};

export default function MyListingsPage() {
  const { user, loading } = useAuth();
  const [items, setItems] = useState(null);
  const [editing, setEditing] = useState(null);
  const [editForm, setEditForm] = useState({});
  const [counterFor, setCounterFor] = useState(null);
  const [counterPrice, setCounterPrice] = useState("");
  const [err, setErr] = useState("");

  const load = async () => {
    try { const { data } = await api.get("/me/listings"); setItems(data); }
    catch (e) { setItems([]); }
  };

  useEffect(() => { if (user) load(); }, [user]);

  if (loading) return <div className="py-24 text-center">Зареждане…</div>;
  if (!user) return <Navigate to="/login?next=/my-listings" replace />;

  const startEdit = (a) => {
    setEditing(a.id);
    setEditForm({ title: a.title, description: a.description, starting_bid_eur: a.starting_bid_eur, reserve_eur: a.reserve_eur || "" });
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
    if (!window.confirm("Приемате ли водещата наддавка?")) return;
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
            <div className="overline text-[hsl(var(--accent))]">Продавач</div>
            <h1 className="font-serif text-4xl lg:text-5xl tracking-tight mt-3">Моите обяви</h1>
            <p className="mt-3 text-sm text-[hsl(var(--ink-muted))]">Управлявайте своите автомобили, одобрения и след-търговите сделки.</p>
          </div>
          <Link to="/sell" className="btn btn-primary flex items-center gap-2" data-testid="new-listing-btn">
            <Plus size={14} /> Нова обява
          </Link>
        </div>

        {err && <p className="mt-4 text-sm text-[hsl(var(--danger))]" data-testid="listings-error">{err}</p>}

        {items === null ? (
          <div className="py-24 text-center text-[hsl(var(--ink-muted))]">Зареждане…</div>
        ) : items.length === 0 ? (
          <div className="mt-12 py-24 text-center rounded-card border border-[hsl(var(--line))]">
            <AlertCircle size={32} className="mx-auto text-[hsl(var(--ink-muted))]" />
            <p className="mt-4 font-serif text-2xl">Все още нямате подадени обяви</p>
            <Link to="/sell" className="btn btn-primary mt-6 inline-flex">Продай автомобил</Link>
          </div>
        ) : (
          <div className="mt-10 space-y-5" data-testid="my-listings-list">
            {items.map((a) => {
              const meta = STATUS_META[a.status] || STATUS_META.pending;
              const Icon = meta.icon;
              const t = a.status === "live" ? timeLeft(a.ends_at) : null;
              const canEdit = a.status === "pending" || a.status === "rejected" || (a.status === "live" && (a.bid_count || 0) === 0);
              const canWithdraw = ["pending", "rejected", "ended", "reserve_not_met"].includes(a.status) || (a.status === "live" && (a.bid_count || 0) === 0);
              const isRNM = a.status === "reserve_not_met";
              const counter = a.counter_status;

              return (
                <div key={a.id} className="rounded-card border border-[hsl(var(--line))] overflow-hidden bg-white" data-testid={`listing-${a.id}`}>
                  <div className="grid grid-cols-1 md:grid-cols-[180px_1fr_auto] gap-0">
                    <div className="aspect-[4/3] md:aspect-auto md:min-h-[160px] bg-[hsl(var(--surface))]">
                      {a.images?.[0] ? <img src={a.images[0]} alt={a.title} className="w-full h-full object-cover" /> : <div className="w-full h-full flex items-center justify-center text-[hsl(var(--ink-muted))] text-xs">Без снимка</div>}
                    </div>
                    <div className="p-5">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className={`pill ${meta.cls}`} data-testid={`status-${a.id}`}><Icon size={11} /> {meta.label}</span>
                        {a.has_reserve && (a.reserve_met ? <span className="pill pill-live">Резервът е достигнат</span> : <span className="pill">С резерв · €{Math.round(a.reserve_eur || 0).toLocaleString("bg-BG")}</span>)}
                        {a.has_reserve === false && <span className="pill">Без резерв</span>}
                        {counter === "pending" && <span className="pill pill-ending">Чака отговор</span>}
                        {counter === "declined" && <span className="pill pill-sold">Отказан контраоферта</span>}
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
                              <strong>Забележка:</strong> {a.rejected_reason}
                            </div>
                          )}
                          {isRNM && counter !== "pending" && counter !== "accepted" && (
                            <div className="mt-4 p-4 rounded-card bg-[hsl(var(--surface))] border border-[hsl(var(--line))]">
                              <div className="overline text-[hsl(var(--accent))]">Търгът приключи под резерв</div>
                              <p className="mt-2 text-sm">Водещата наддавка €{Math.round(a.current_bid_eur).toLocaleString("bg-BG")} не достигна резерва ви от €{Math.round(a.reserve_eur || 0).toLocaleString("bg-BG")}. Можете да приемете, да предложите своя цена, или да оттеглите.</p>
                              <div className="mt-3 flex flex-wrap gap-2">
                                <button onClick={() => acceptHighBid(a.id)} className="btn btn-accent !py-2 !px-4 text-xs flex items-center gap-2" data-testid={`accept-high-${a.id}`}>
                                  <CheckCircle2 size={13} /> Приеми {formatEUR(a.current_bid_eur)}
                                </button>
                                <button onClick={() => setCounterFor(a.id)} className="btn btn-primary !py-2 !px-4 text-xs flex items-center gap-2" data-testid={`counter-${a.id}`}>
                                  <Gift size={13} /> Контраоферта
                                </button>
                              </div>
                              {counterFor === a.id && (
                                <div className="mt-4 flex gap-2">
                                  <input type="number" value={counterPrice} onChange={(e) => setCounterPrice(e.target.value)} placeholder="Вашата цена в €" className="flex-1 border border-[hsl(var(--line))] h-10 px-3 text-sm" data-testid={`counter-price-${a.id}`} />
                                  <button onClick={() => sendCounter(a.id)} className="btn btn-accent !py-2 !px-4 text-xs" data-testid={`send-counter-${a.id}`}>Изпрати</button>
                                  <button onClick={() => { setCounterFor(null); setCounterPrice(""); }} className="btn btn-secondary !py-2 !px-4 text-xs">Отказ</button>
                                </div>
                              )}
                            </div>
                          )}
                          {counter === "pending" && (
                            <p className="mt-3 text-xs text-[hsl(var(--ink-muted))]">Очаква отговор за контраоферта €{Math.round(a.counter_offer_eur).toLocaleString("bg-BG")}.</p>
                          )}

                          <div className="mt-4 flex gap-2 flex-wrap">
                            {canEdit && <button onClick={() => startEdit(a)} className="btn btn-secondary !py-2 !px-3 text-xs flex items-center gap-1.5" data-testid={`edit-${a.id}`}><Edit3 size={12} /> Редактирай</button>}
                            {canWithdraw && <button onClick={() => withdraw(a.id)} className="btn btn-secondary !py-2 !px-3 text-xs flex items-center gap-1.5" data-testid={`withdraw-${a.id}`}><Trash2 size={12} /> Оттегли</button>}
                          </div>
                        </>
                      )}
                    </div>
                    <div className="p-5 md:border-l border-[hsl(var(--line))] flex flex-col justify-center items-start md:items-end gap-2 min-w-[200px]">
                      {a.status === "live" && (<>
                        <div className="overline text-[hsl(var(--ink-muted))]">Текуща</div>
                        <div className="font-serif text-2xl">{formatEUR(a.current_bid_eur)}</div>
                        <div className="text-xs text-[hsl(var(--ink-muted))]">{a.bid_count || 0} наддав. · {t?.label}</div>
                      </>)}
                      {a.status === "sold" && (<>
                        <div className="overline text-[hsl(var(--ink-muted))]">Продаден за</div>
                        <div className="font-serif text-2xl">{formatEUR(a.current_bid_eur)}</div>
                      </>)}
                      {(a.status === "pending" || a.status === "rejected" || a.status === "withdrawn") && (<>
                        <div className="overline text-[hsl(var(--ink-muted))]">Начална</div>
                        <div className="font-serif text-2xl">{formatEUR(a.starting_bid_eur)}</div>
                      </>)}
                      {isRNM && (<>
                        <div className="overline text-[hsl(var(--ink-muted))]">Водеща оферта</div>
                        <div className="font-serif text-2xl">{formatEUR(a.current_bid_eur)}</div>
                      </>)}
                      {(a.status === "live" || a.status === "sold" || isRNM) && <Link to={`/auctions/${a.id}`} className="btn btn-secondary !py-2 !px-4 mt-1">Виж обявата</Link>}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </main>
  );
}
