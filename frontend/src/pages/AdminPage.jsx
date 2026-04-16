import React, { useEffect, useState, useCallback } from "react";
import { Navigate, Link } from "react-router-dom";
import { Check, X, Clock, AlertCircle, DollarSign, Archive, Ban, Edit3, Trash2, RotateCcw, Search, List } from "lucide-react";
import { useAuth, formatError } from "../lib/auth";
import { api, formatEUR, formatKM } from "../lib/apiClient";
import AdminEditModal from "../components/AdminEditModal";

const STATUS_LABELS = {
  pending: "Очаква",
  live: "Активен",
  ended: "Приключил",
  sold: "Продаден",
  reserve_not_met: "Резервът не е достигнат",
  withdrawn: "Оттеглен",
  removed: "Премахнат",
  rejected: "Отказан",
};

export default function AdminPage() {
  const { user, loading } = useAuth();
  const [tab, setTab] = useState("pending");
  const [pending, setPending] = useState([]);
  const [sold, setSold] = useState([]);
  const [allListings, setAllListings] = useState([]);
  const [allQuery, setAllQuery] = useState("");
  const [allStatusFilter, setAllStatusFilter] = useState("");
  const [rejectingId, setRejectingId] = useState(null);
  const [reason, setReason] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(null);
  const [editingId, setEditingId] = useState(null);

  const loadPending = useCallback(async () => {
    try { const { data } = await api.get("/admin/pending"); setPending(data); }
    catch (e) { setErr(formatError(e)); }
  }, []);
  const loadSold = useCallback(async () => {
    try { const { data } = await api.get("/admin/sold"); setSold(data); }
    catch (e) { setErr(formatError(e)); }
  }, []);
  const loadAll = useCallback(async () => {
    try {
      const params = {};
      if (allQuery) params.q = allQuery;
      if (allStatusFilter) params.status = allStatusFilter;
      const { data } = await api.get("/admin/auctions", { params });
      setAllListings(data);
    } catch (e) { setErr(formatError(e)); }
  }, [allQuery, allStatusFilter]);

  useEffect(() => {
    if (user?.role === "admin") {
      loadPending();
      loadSold();
      loadAll();
    }
  }, [user, loadPending, loadSold, loadAll]);

  if (loading) return <div className="py-24 text-center">Зареждане…</div>;
  if (!user) return <Navigate to="/login?next=/admin" replace />;
  if (user.role !== "admin") {
    return (
      <main className="py-24" data-testid="admin-denied">
        <div className="max-w-md mx-auto text-center px-6">
          <AlertCircle size={32} className="mx-auto text-[hsl(var(--danger))]" />
          <h1 className="font-serif text-3xl mt-4">Достъпът е ограничен</h1>
          <p className="mt-3 text-sm text-[hsl(var(--ink-muted))]">Тази страница е достъпна само за администратори.</p>
          <Link to="/" className="btn btn-primary mt-6 inline-flex">Към началото</Link>
        </div>
      </main>
    );
  }

  const approve = async (id) => {
    setErr(""); setBusy(id);
    try { await api.post(`/admin/auctions/${id}/approve`); await Promise.all([loadPending(), loadAll()]); }
    catch (e) { setErr(formatError(e)); }
    finally { setBusy(null); }
  };
  const reject = async (id) => {
    setErr(""); setBusy(id);
    try {
      await api.post(`/admin/auctions/${id}/reject`, { reason });
      setRejectingId(null); setReason("");
      await Promise.all([loadPending(), loadAll()]);
    } catch (e) { setErr(formatError(e)); }
    finally { setBusy(null); }
  };
  const capturePremium = async (id) => {
    setErr(""); setBusy(id);
    try { await api.post(`/admin/auctions/${id}/capture-premium`); await loadSold(); }
    catch (e) { setErr(formatError(e)); }
    finally { setBusy(null); }
  };
  const releaseAll = async (id) => {
    setErr(""); setBusy(id);
    try { await api.post(`/admin/auctions/${id}/finalize`); await loadSold(); }
    catch (e) { setErr(formatError(e)); }
    finally { setBusy(null); }
  };
  const removeListing = async (id) => {
    if (!window.confirm('Сигурни ли сте, че искате да свалите тази обява от публичния сайт? Тя ще остане в базата със статус „Премахната“.')) return;
    setErr(""); setBusy(id);
    try { await api.post(`/admin/auctions/${id}/remove`); await Promise.all([loadAll(), loadPending()]); }
    catch (e) { setErr(formatError(e)); }
    finally { setBusy(null); }
  };
  const restoreListing = async (id) => {
    setErr(""); setBusy(id);
    try { await api.post(`/admin/auctions/${id}/restore`); await Promise.all([loadAll(), loadPending()]); }
    catch (e) { setErr(formatError(e)); }
    finally { setBusy(null); }
  };

  const tabs = [
    { k: "pending", label: `Очакващи (${pending.length})`, icon: Clock },
    { k: "all", label: `Всички обяви (${allListings.length})`, icon: List },
    { k: "sold", label: `Продадени (${sold.length})`, icon: Archive },
  ];

  return (
    <main data-testid="admin-page">
      <div className="max-w-[1200px] mx-auto px-4 sm:px-6 lg:px-10 py-16">
        <div className="overline text-[hsl(var(--accent))]">Администратор</div>
        <h1 className="font-serif text-4xl lg:text-5xl mt-3 tracking-tight">Контролен панел</h1>

        <div className="mt-8 inline-flex rounded-card border border-[hsl(var(--line))] overflow-hidden bg-white flex-wrap">
          {tabs.map((t, i) => {
            const Icon = t.icon;
            return (
              <button
                key={t.k}
                onClick={() => setTab(t.k)}
                className={`px-5 py-2.5 text-sm font-medium flex items-center gap-2 ${tab === t.k ? "bg-[hsl(var(--ink))] text-white" : ""} ${i > 0 ? "border-l border-[hsl(var(--line))]" : ""}`}
                data-testid={`tab-${t.k}`}
              >
                <Icon size={14} /> {t.label}
              </button>
            );
          })}
        </div>

        {err && <p className="mt-4 text-sm text-[hsl(var(--danger))]">{err}</p>}

        {tab === "pending" && (
          <div className="mt-10">
            {pending.length === 0 ? (
              <EmptyState icon={Clock} title="Няма очакващи обяви" sub="Всичко е подредено." />
            ) : (
              <div className="space-y-5" data-testid="pending-list">
                {pending.map((a) => (
                  <div key={a.id} className="rounded-card border border-[hsl(var(--line))] overflow-hidden bg-white" data-testid={`pending-${a.id}`}>
                    <div className="grid grid-cols-1 md:grid-cols-[260px_1fr] gap-0">
                      <div className="aspect-[4/3] md:aspect-auto bg-[hsl(var(--surface))]">
                        {a.images?.[0] ? (
                          <img src={a.images[0]} alt={a.title} className="w-full h-full object-cover" />
                        ) : (
                          <div className="w-full h-full flex items-center justify-center text-[hsl(var(--ink-muted))] text-xs">Без снимка</div>
                        )}
                      </div>
                      <div className="p-6">
                        <div className="overline text-[hsl(var(--ink-muted))]">{a.make} · {a.body_type} · {a.city}</div>
                        <h3 className="font-serif text-2xl mt-2">{a.title}</h3>
                        <div className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-2 text-sm text-[hsl(var(--ink-muted))]">
                          <span>{a.year} г.</span>
                          <span>{formatKM(a.mileage_km)}</span>
                          <span>{a.fuel} · {a.transmission}</span>
                          <span>{a.power_hp} к.с.</span>
                        </div>
                        <p className="mt-4 text-sm leading-relaxed line-clamp-3">{a.description}</p>
                        <div className="mt-4 flex items-center justify-between">
                          <div>
                            <div className="overline text-[hsl(var(--ink-muted))]">Начална цена</div>
                            <div className="font-serif text-xl">{formatEUR(a.starting_bid_eur)}</div>
                          </div>
                          <div className="text-xs text-[hsl(var(--ink-muted))] font-mono">От {a.seller_name}</div>
                        </div>

                        {rejectingId === a.id ? (
                          <div className="mt-5 rounded-card border border-[hsl(var(--line))] p-4 bg-[hsl(var(--surface))]">
                            <label className="overline text-[hsl(var(--ink-muted))] block mb-2">Причина за отказ</label>
                            <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={2} className="w-full border border-[hsl(var(--line))] p-3 text-sm" data-testid={`reject-reason-${a.id}`} />
                            <div className="mt-3 flex gap-2 justify-end">
                              <button onClick={() => { setRejectingId(null); setReason(""); }} className="btn btn-secondary !py-2 !px-4">Отказ</button>
                              <button onClick={() => reject(a.id)} disabled={busy === a.id} className="btn btn-primary !py-2 !px-4" data-testid={`reject-confirm-${a.id}`}>Изпрати отказ</button>
                            </div>
                          </div>
                        ) : (
                          <div className="mt-5 flex gap-2 flex-wrap">
                            <button onClick={() => approve(a.id)} disabled={busy === a.id} className="btn btn-accent !py-2 !px-4 flex items-center gap-2" data-testid={`approve-${a.id}`}>
                              <Check size={14} /> Одобри и стартирай
                            </button>
                            <button onClick={() => setEditingId(a.id)} className="btn btn-secondary !py-2 !px-4 flex items-center gap-2" data-testid={`edit-pending-${a.id}`}>
                              <Edit3 size={14} /> Редактирай
                            </button>
                            <button onClick={() => setRejectingId(a.id)} className="btn btn-secondary !py-2 !px-4 flex items-center gap-2" data-testid={`reject-${a.id}`}>
                              <X size={14} /> Откажи
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {tab === "all" && (
          <div className="mt-10">
            <div className="flex flex-wrap gap-3 items-end mb-5">
              <div className="flex-1 min-w-[220px] relative">
                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[hsl(var(--ink-muted))]" />
                <input
                  type="text"
                  value={allQuery}
                  onChange={(e) => setAllQuery(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && loadAll()}
                  placeholder="Търсене по заглавие, марка, модел, продавач..."
                  className="input pl-9"
                  data-testid="admin-all-search"
                />
              </div>
              <select value={allStatusFilter} onChange={(e) => setAllStatusFilter(e.target.value)} className="input !w-auto" data-testid="admin-all-status-filter">
                <option value="">Всички статуси</option>
                {Object.entries(STATUS_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
              <button onClick={loadAll} className="btn btn-primary !py-2 !px-4" data-testid="admin-all-refresh">Търси</button>
            </div>

            {allListings.length === 0 ? (
              <EmptyState icon={List} title="Няма обяви" sub="Опитайте с различно търсене." />
            ) : (
              <div className="rounded-card border border-[hsl(var(--line))] overflow-hidden bg-white" data-testid="all-listings">
                <div className="hidden md:grid grid-cols-[1.8fr_0.7fr_0.9fr_0.7fr_1.3fr] gap-3 px-5 py-3 rule-b bg-[hsl(var(--surface))] overline text-[hsl(var(--ink-muted))]">
                  <span>Обява</span>
                  <span>Статус</span>
                  <span>Текуща цена</span>
                  <span>Продавач</span>
                  <span>Действия</span>
                </div>
                {allListings.map((a) => (
                  <div key={a.id} className="grid grid-cols-1 md:grid-cols-[1.8fr_0.7fr_0.9fr_0.7fr_1.3fr] gap-3 items-center p-4 rule-b last:border-b-0" data-testid={`listing-row-${a.id}`}>
                    <div className="flex items-center gap-3 min-w-0">
                      {a.images?.[0] ? <img src={a.images[0]} className="w-14 h-10 object-cover rounded-md shrink-0" alt="" /> : <div className="w-14 h-10 bg-[hsl(var(--surface))] rounded-md shrink-0" />}
                      <div className="min-w-0">
                        <div className="font-semibold text-sm truncate">{a.title}</div>
                        <div className="text-xs text-[hsl(var(--ink-muted))]">{a.make} · {a.year} · {a.city}</div>
                      </div>
                    </div>
                    <div>
                      <span className={`pill text-xs ${a.status === "live" ? "pill-live" : ""}`} data-testid={`status-${a.id}`}>{STATUS_LABELS[a.status] || a.status}</span>
                    </div>
                    <div className="font-serif text-base">{formatEUR(a.current_bid_eur || 0)}</div>
                    <div className="text-xs truncate">{a.seller_name || "—"}</div>
                    <div className="flex gap-2 flex-wrap justify-end md:justify-start">
                      <button onClick={() => setEditingId(a.id)} className="btn btn-secondary !py-1.5 !px-3 text-xs flex items-center gap-1" data-testid={`edit-${a.id}`}>
                        <Edit3 size={12} /> Редактирай
                      </button>
                      {a.status === "pending" && (
                        <button onClick={() => approve(a.id)} disabled={busy === a.id} className="btn btn-accent !py-1.5 !px-3 text-xs flex items-center gap-1" data-testid={`quick-approve-${a.id}`}>
                          <Check size={12} /> Одобри
                        </button>
                      )}
                      {a.status === "removed" || a.status === "withdrawn" ? (
                        <button onClick={() => restoreListing(a.id)} disabled={busy === a.id} className="btn btn-secondary !py-1.5 !px-3 text-xs flex items-center gap-1" data-testid={`restore-${a.id}`}>
                          <RotateCcw size={12} /> Възстанови
                        </button>
                      ) : a.status !== "sold" ? (
                        <button onClick={() => removeListing(a.id)} disabled={busy === a.id} className="btn btn-secondary !py-1.5 !px-3 text-xs flex items-center gap-1 !border-[hsl(var(--danger))] !text-[hsl(var(--danger))]" data-testid={`remove-${a.id}`}>
                          <Trash2 size={12} /> Свали
                        </button>
                      ) : null}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {tab === "sold" && (
          <div className="mt-10">
            {sold.length === 0 ? (
              <EmptyState icon={Archive} title="Няма продадени търгове" sub="Когато търгове бъдат финализирани, ще се появят тук." />
            ) : (
              <div className="rounded-card border border-[hsl(var(--line))] overflow-hidden bg-white" data-testid="sold-list">
                <div className="hidden md:grid grid-cols-[1.6fr_1fr_0.9fr_0.8fr_1.2fr] gap-4 px-5 py-3 rule-b bg-[hsl(var(--surface))] overline text-[hsl(var(--ink-muted))]">
                  <span>Обява</span>
                  <span>Купувач</span>
                  <span>Финална цена</span>
                  <span>Комисионна 2%</span>
                  <span>Действие</span>
                </div>
                {sold.map((a) => {
                  const captured = a.premium_captured;
                  const status = a.winning_bid_preauth_status;
                  const commission = a.commission_eur || 0;
                  return (
                    <div key={a.id} className="grid grid-cols-1 md:grid-cols-[1.6fr_1fr_0.9fr_0.8fr_1.2fr] gap-4 items-center p-5 rule-b last:border-b-0" data-testid={`sold-${a.id}`}>
                      <div className="flex items-center gap-3 min-w-0">
                        {a.images?.[0] && <img src={a.images[0]} className="w-14 h-10 object-cover rounded-md shrink-0" alt="" />}
                        <div className="min-w-0">
                          <div className="font-semibold text-sm truncate">{a.title}</div>
                          <div className="text-xs text-[hsl(var(--ink-muted))]">{a.make} · {a.year}</div>
                        </div>
                      </div>
                      <div className="text-sm">
                        <div>{a.winner_name || "—"}</div>
                        <div className="text-xs text-[hsl(var(--ink-muted))] font-mono truncate">{a.winner_email || "—"}</div>
                      </div>
                      <div className="font-serif text-lg">{formatEUR(a.current_bid_eur)}</div>
                      <div>
                        <div className="font-serif text-lg">{formatEUR(commission)}</div>
                        <div className="text-[11px] text-[hsl(var(--ink-muted))] font-mono">
                          preauth: {status || "—"}
                        </div>
                      </div>
                      <div className="flex flex-col md:items-end gap-2">
                        {captured ? (
                          <span className="pill pill-live" data-testid={`captured-${a.id}`}><Check size={12} /> Преведено</span>
                        ) : status === "authorized" ? (
                          <div className="flex gap-2 flex-wrap">
                            <button onClick={() => capturePremium(a.id)} disabled={busy === a.id} className="btn btn-accent !py-2 !px-3 text-xs flex items-center gap-1" data-testid={`capture-${a.id}`}>
                              <DollarSign size={12} /> Capture {formatEUR(commission)}
                            </button>
                            <button onClick={() => releaseAll(a.id)} disabled={busy === a.id} className="btn btn-secondary !py-2 !px-3 text-xs flex items-center gap-1" data-testid={`release-${a.id}`}>
                              <Ban size={12} /> Освободи
                            </button>
                          </div>
                        ) : (
                          <span className="text-xs text-[hsl(var(--ink-muted))]">Preauth: {status || "—"}</span>
                        )}
                        <button onClick={() => setEditingId(a.id)} className="btn btn-secondary !py-1.5 !px-3 text-xs flex items-center gap-1" data-testid={`edit-sold-${a.id}`}>
                          <Edit3 size={12} /> Редактирай
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>

      {editingId && (
        <AdminEditModal
          auctionId={editingId}
          onClose={() => setEditingId(null)}
          onSaved={() => { loadPending(); loadSold(); loadAll(); }}
        />
      )}
    </main>
  );
}

function EmptyState({ icon: Icon, title, sub }) {
  return (
    <div className="py-24 text-center rounded-card border border-[hsl(var(--line))]">
      <Icon size={32} className="mx-auto text-[hsl(var(--ink-muted))]" />
      <p className="mt-4 font-serif text-2xl">{title}</p>
      <p className="mt-2 text-sm text-[hsl(var(--ink-muted))]">{sub}</p>
    </div>
  );
}
