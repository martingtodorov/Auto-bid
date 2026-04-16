import React, { useEffect, useState } from "react";
import { Navigate, Link } from "react-router-dom";
import { Check, X, Clock, AlertCircle } from "lucide-react";
import { useAuth, formatError } from "../lib/auth";
import { api, formatEUR, formatKM } from "../lib/apiClient";

export default function AdminPage() {
  const { user, loading } = useAuth();
  const [items, setItems] = useState([]);
  const [rejectingId, setRejectingId] = useState(null);
  const [reason, setReason] = useState("");
  const [err, setErr] = useState("");

  const load = async () => {
    try {
      const { data } = await api.get("/admin/pending");
      setItems(data);
    } catch (e) { setErr(formatError(e)); }
  };

  useEffect(() => { if (user?.role === "admin") load(); }, [user]);

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
    setErr("");
    try {
      await api.post(`/admin/auctions/${id}/approve`);
      load();
    } catch (e) { setErr(formatError(e)); }
  };

  const reject = async (id) => {
    setErr("");
    try {
      await api.post(`/admin/auctions/${id}/reject`, { reason });
      setRejectingId(null);
      setReason("");
      load();
    } catch (e) { setErr(formatError(e)); }
  };

  return (
    <main data-testid="admin-page">
      <div className="max-w-[1200px] mx-auto px-4 sm:px-6 lg:px-10 py-16">
        <div className="overline text-[hsl(var(--accent))]">Администратор</div>
        <h1 className="font-serif text-4xl lg:text-5xl mt-3 tracking-tight">Модерация на обяви</h1>
        <p className="mt-3 text-sm text-[hsl(var(--ink-muted))]">
          Преглед на подадените за одобрение автомобили. Одобрените стартират активен търг с продължителност 7 дни.
        </p>

        {err && <p className="mt-4 text-sm text-[hsl(var(--danger))]">{err}</p>}

        <div className="mt-10">
          {items.length === 0 ? (
            <div className="py-24 text-center rounded-card border border-[hsl(var(--line))]">
              <Clock size={32} className="mx-auto text-[hsl(var(--ink-muted))]" />
              <p className="mt-4 font-serif text-2xl">Няма очакващи обяви</p>
              <p className="mt-2 text-sm text-[hsl(var(--ink-muted))]">Всичко е подредено.</p>
            </div>
          ) : (
            <div className="space-y-5" data-testid="pending-list">
              {items.map((a) => (
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
                            <button onClick={() => reject(a.id)} className="btn btn-primary !py-2 !px-4" data-testid={`reject-confirm-${a.id}`}>Изпрати отказ</button>
                          </div>
                        </div>
                      ) : (
                        <div className="mt-5 flex gap-2">
                          <button onClick={() => approve(a.id)} className="btn btn-accent !py-2 !px-4 flex items-center gap-2" data-testid={`approve-${a.id}`}>
                            <Check size={14} /> Одобри и стартирай
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
      </div>
    </main>
  );
}
