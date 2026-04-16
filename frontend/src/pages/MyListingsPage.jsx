import React, { useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { Plus, Clock, CheckCircle2, XCircle, Gavel, Archive, AlertCircle } from "lucide-react";
import { useAuth } from "../lib/auth";
import { api, formatEUR, timeLeft } from "../lib/apiClient";

const STATUS_META = {
  pending:  { label: "Очаква одобрение", icon: Clock, cls: "text-[hsl(var(--ink-muted))] border-[hsl(var(--line))]" },
  live:     { label: "Активен търг", icon: Gavel, cls: "text-[hsl(var(--accent))] border-[hsl(var(--accent))]/40 bg-[hsl(var(--accent-soft))]" },
  sold:     { label: "Продаден", icon: CheckCircle2, cls: "text-[hsl(var(--success))] border-[hsl(var(--success))]/40" },
  ended:    { label: "Приключил", icon: Archive, cls: "text-[hsl(var(--ink-muted))] border-[hsl(var(--line))]" },
  rejected: { label: "Отказан", icon: XCircle, cls: "text-[hsl(var(--danger))] border-[hsl(var(--danger))]/40" },
};

export default function MyListingsPage() {
  const { user, loading } = useAuth();
  const [items, setItems] = useState(null);

  useEffect(() => {
    if (!user) return;
    api.get("/me/listings").then((r) => setItems(r.data)).catch(() => setItems([]));
  }, [user]);

  if (loading) return <div className="py-24 text-center">Зареждане…</div>;
  if (!user) return <Navigate to="/login?next=/my-listings" replace />;

  return (
    <main data-testid="my-listings-page">
      <div className="max-w-[1200px] mx-auto px-4 sm:px-6 lg:px-10 py-16">
        <div className="flex items-end justify-between gap-4 flex-wrap">
          <div>
            <div className="overline text-[hsl(var(--accent))]">Продавач</div>
            <h1 className="font-serif text-4xl lg:text-5xl tracking-tight mt-3">Моите обяви</h1>
            <p className="mt-3 text-sm text-[hsl(var(--ink-muted))]">Всички автомобили, които сте подали за търг.</p>
          </div>
          <Link to="/sell" className="btn btn-primary flex items-center gap-2" data-testid="new-listing-btn">
            <Plus size={14} /> Нова обява
          </Link>
        </div>

        {items === null ? (
          <div className="py-24 text-center text-[hsl(var(--ink-muted))]">Зареждане…</div>
        ) : items.length === 0 ? (
          <div className="mt-12 py-24 text-center rounded-card border border-[hsl(var(--line))]">
            <AlertCircle size={32} className="mx-auto text-[hsl(var(--ink-muted))]" />
            <p className="mt-4 font-serif text-2xl">Все още нямате подадени обяви</p>
            <p className="mt-2 text-sm text-[hsl(var(--ink-muted))]">Създайте първата си обява за няколко минути.</p>
            <Link to="/sell" className="btn btn-primary mt-6 inline-flex">Продай автомобил</Link>
          </div>
        ) : (
          <div className="mt-10 space-y-4" data-testid="my-listings-list">
            {items.map((a) => {
              const meta = STATUS_META[a.status] || STATUS_META.pending;
              const Icon = meta.icon;
              const t = a.status === "live" ? timeLeft(a.ends_at) : null;
              return (
                <div key={a.id} className="rounded-card border border-[hsl(var(--line))] overflow-hidden bg-white" data-testid={`listing-${a.id}`}>
                  <div className="grid grid-cols-1 md:grid-cols-[180px_1fr_auto] gap-0">
                    <div className="aspect-[4/3] md:aspect-auto md:min-h-[140px] bg-[hsl(var(--surface))]">
                      {a.images?.[0] ? (
                        <img src={a.images[0]} alt={a.title} className="w-full h-full object-cover" />
                      ) : (
                        <div className="w-full h-full flex items-center justify-center text-[hsl(var(--ink-muted))] text-xs">Без снимка</div>
                      )}
                    </div>
                    <div className="p-5">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className={`pill ${meta.cls}`} data-testid={`status-${a.id}`}>
                          <Icon size={11} /> {meta.label}
                        </span>
                        {a.has_reserve && (a.reserve_met ? <span className="pill pill-live">Резервът е достигнат</span> : <span className="pill">С резерв{a.reserve_eur ? ` · €${Math.round(a.reserve_eur).toLocaleString('bg-BG')}` : ""}</span>)}
                        {a.has_reserve === false && <span className="pill">Без резерв</span>}
                      </div>
                      <h3 className="font-serif text-xl mt-3">{a.title}</h3>
                      <div className="mt-2 text-sm text-[hsl(var(--ink-muted))]">
                        {a.make} · {a.year} г. · {a.city}
                      </div>
                      {a.status === "rejected" && a.rejected_reason && (
                        <div className="mt-3 text-xs rounded-card bg-[hsl(0_74%_97%)] border border-[hsl(var(--danger))]/30 p-3 text-[hsl(var(--danger))]" data-testid={`reject-reason-${a.id}`}>
                          <strong>Забележка:</strong> {a.rejected_reason}
                        </div>
                      )}
                    </div>
                    <div className="p-5 md:border-l border-[hsl(var(--line))] flex flex-col justify-center items-start md:items-end gap-2 min-w-[180px]">
                      {a.status === "live" && (
                        <>
                          <div className="overline text-[hsl(var(--ink-muted))]">Текуща</div>
                          <div className="font-serif text-2xl">{formatEUR(a.current_bid_eur)}</div>
                          <div className="text-xs text-[hsl(var(--ink-muted))]">{a.bid_count || 0} наддав. · остава {t?.label}</div>
                        </>
                      )}
                      {a.status === "sold" && (
                        <>
                          <div className="overline text-[hsl(var(--ink-muted))]">Продаден за</div>
                          <div className="font-serif text-2xl">{formatEUR(a.current_bid_eur)}</div>
                          {a.premium_captured && <div className="text-xs text-[hsl(var(--ink-muted))]">Комисионна €{Math.round(a.premium_amount_eur || 0)} преведена</div>}
                        </>
                      )}
                      {a.status === "pending" && (
                        <>
                          <div className="overline text-[hsl(var(--ink-muted))]">Начална</div>
                          <div className="font-serif text-2xl">{formatEUR(a.starting_bid_eur)}</div>
                        </>
                      )}
                      {(a.status === "live" || a.status === "sold") && (
                        <Link to={`/auctions/${a.id}`} className="btn btn-secondary !py-2 !px-4 mt-2">Виж обявата</Link>
                      )}
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
