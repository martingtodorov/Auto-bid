import React, { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import { Inbox, Check, X, Star, FileEdit, RefreshCw } from "lucide-react";
import { api } from "../lib/apiClient";
import { formatError } from "../lib/auth";
import { auctionUrl } from "../lib/auctionUrl";

const TYPE_META = {
  promotion: { label: "Промотиране", icon: Star, cls: "text-amber-600 border-amber-300 bg-amber-50" },
  text_change: { label: "Промяна на текст", icon: FileEdit, cls: "text-[hsl(var(--accent))] border-[hsl(var(--accent))]/40 bg-[hsl(var(--accent-soft))]" },
};

const STATUS_META = {
  pending: { label: "Чака", cls: "border-[hsl(var(--line))]" },
  approved: { label: "Одобрена", cls: "text-[hsl(var(--success))] border-[hsl(var(--success))]/40" },
  rejected: { label: "Отказана", cls: "text-[hsl(var(--danger))] border-[hsl(var(--danger))]/40" },
  cancelled: { label: "Оттеглена", cls: "text-[hsl(var(--ink-muted))] border-[hsl(var(--line))]" },
};

export default function AdminSellerRequestsTab() {
  const [items, setItems] = useState([]);
  const [status, setStatus] = useState("pending");
  const [type, setType] = useState("");
  const [busy, setBusy] = useState(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);
  // Admin-only manual translations for text_change approvals: keyed by request id.
  const [translations, setTranslations] = useState({});

  const setTr = (id, lang, value) => {
    setTranslations((prev) => ({ ...prev, [id]: { ...(prev[id] || {}), [lang]: value } }));
  };

  const load = useCallback(async () => {
    setLoading(true); setErr("");
    try {
      const params = {};
      if (status) params.status = status;
      if (type) params.type = type;
      const { data } = await api.get("/admin/seller-requests", { params });
      setItems(data || []);
    } catch (e) { setErr(formatError(e)); }
    finally { setLoading(false); }
  }, [status, type]);

  useEffect(() => { load(); }, [load]);

  const approve = async (id, type) => {
    if (!window.confirm("Одобряване на заявката?")) return;
    setBusy(id); setErr("");
    try {
      const body = {};
      if (type === "text_change") {
        const tr = translations[id] || {};
        if (tr.ro != null) body.description_ro = tr.ro;
        if (tr.en != null) body.description_en = tr.en;
      }
      await api.post(`/admin/seller-requests/${id}/approve`, body);
      await load();
    } catch (e) { setErr(formatError(e)); }
    finally { setBusy(null); }
  };

  const reject = async (id) => {
    const reason = window.prompt("Причина за отказ (мин. 3 символа):");
    if (!reason || reason.trim().length < 3) return;
    setBusy(id); setErr("");
    try { await api.post(`/admin/seller-requests/${id}/reject`, { reason: reason.trim() }); await load(); }
    catch (e) { setErr(formatError(e)); }
    finally { setBusy(null); }
  };

  return (
    <div className="mt-10 space-y-5" data-testid="admin-seller-requests-tab">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <div className="overline text-[hsl(var(--accent))]">Модерация</div>
          <h2 className="font-serif text-3xl">Заявки от продавачи</h2>
          <p className="mt-2 text-sm text-[hsl(var(--ink-muted))] max-w-2xl">
            Продавачите могат да поискат промотиране на обявата си или ревизия на текста. Модераторите преглеждат и прилагат.
          </p>
        </div>
        <div className="flex gap-2 items-center flex-wrap">
          <select value={status} onChange={(e) => setStatus(e.target.value)} className="input !w-auto" data-testid="requests-status-filter">
            <option value="pending">Чакащи</option>
            <option value="approved">Одобрени</option>
            <option value="rejected">Отказани</option>
            <option value="cancelled">Оттеглени</option>
            <option value="">Всички</option>
          </select>
          <select value={type} onChange={(e) => setType(e.target.value)} className="input !w-auto" data-testid="requests-type-filter">
            <option value="">Всички типове</option>
            <option value="promotion">Промотиране</option>
            <option value="text_change">Промяна на текст</option>
          </select>
          <button onClick={load} className="btn btn-primary !py-2 !px-4 flex items-center gap-2" data-testid="requests-refresh">
            <RefreshCw size={14} /> Опресни
          </button>
        </div>
      </div>

      {err && <p className="text-sm text-[hsl(var(--danger))]" data-testid="requests-error">{err}</p>}

      {loading ? (
        <div className="py-24 text-center text-[hsl(var(--ink-muted))]">Зареждане…</div>
      ) : items.length === 0 ? (
        <div className="py-24 text-center rounded-card border border-[hsl(var(--line))]" data-testid="requests-empty">
          <Inbox size={32} className="mx-auto text-[hsl(var(--ink-muted))]" />
          <p className="mt-4 font-serif text-2xl">Няма заявки</p>
        </div>
      ) : (
        <div className="space-y-4" data-testid="requests-list">
          {items.map((r) => {
            const tMeta = TYPE_META[r.type] || { label: r.type, icon: Inbox, cls: "" };
            const sMeta = STATUS_META[r.status] || STATUS_META.pending;
            const TIcon = tMeta.icon;
            return (
              <div key={r.id} className="rounded-card border border-[hsl(var(--line))] bg-white p-5" data-testid={`request-${r.id}`}>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className={`pill text-xs ${tMeta.cls}`}><TIcon size={11} /> {tMeta.label}</span>
                  <span className={`pill text-xs ${sMeta.cls}`}>{sMeta.label}</span>
                  <span className="text-xs font-mono text-[hsl(var(--ink-muted))]">{r.created_at ? new Date(r.created_at).toLocaleString("bg-BG") : ""}</span>
                </div>
                <h3 className="font-serif text-xl mt-3">
                  <Link to={auctionUrl({ id: r.auction_id, title: r.auction_title })} className="hover:text-[hsl(var(--accent))]" data-testid={`request-auction-${r.id}`}>
                    {r.auction_title}
                  </Link>
                </h3>
                <div className="text-sm text-[hsl(var(--ink-muted))] mt-1">от {r.seller_name}</div>

                {r.type === "text_change" && (
                  <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4">
                    {r.payload?.title && (
                      <div className="rounded-card border border-[hsl(var(--line))] p-3 bg-[hsl(var(--surface))]">
                        <div className="overline text-[hsl(var(--ink-muted))] mb-1">Ново заглавие</div>
                        <div className="text-sm font-semibold" data-testid={`request-new-title-${r.id}`}>{r.payload.title}</div>
                        <div className="mt-2 text-xs text-[hsl(var(--ink-muted))] line-through">{r.payload.current_title}</div>
                      </div>
                    )}
                    {r.payload?.description && (
                      <div className="rounded-card border border-[hsl(var(--line))] p-3 bg-[hsl(var(--surface))]">
                        <div className="overline text-[hsl(var(--ink-muted))] mb-1">Ново описание</div>
                        <div className="text-sm whitespace-pre-wrap" data-testid={`request-new-desc-${r.id}`}>{r.payload.description.slice(0, 400)}{r.payload.description.length > 400 ? "…" : ""}</div>
                      </div>
                    )}
                  </div>
                )}

                {r.payload?.note && (
                  <div className="mt-3 text-xs text-[hsl(var(--ink-muted))]">
                    <strong>Бележка:</strong> {r.payload.note}
                  </div>
                )}

                {r.type === "text_change" && r.status === "pending" && (
                  <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-3" data-testid={`request-translations-${r.id}`}>
                    <div>
                      <label className="overline text-[hsl(var(--ink-muted))] mb-1 block">🇷🇴 Описание (Romanian) — само админ</label>
                      <textarea
                        rows={3}
                        value={(translations[r.id] || {}).ro || ""}
                        onChange={(e) => setTr(r.id, "ro", e.target.value)}
                        placeholder="Опционален ръчен превод за RO сайта. Ако е празно, ще се използва автоматичен превод."
                        className="input font-mono text-xs"
                        data-testid={`request-translation-ro-${r.id}`}
                      />
                    </div>
                    <div>
                      <label className="overline text-[hsl(var(--ink-muted))] mb-1 block">🇬🇧 Description (English) — admin only</label>
                      <textarea
                        rows={3}
                        value={(translations[r.id] || {}).en || ""}
                        onChange={(e) => setTr(r.id, "en", e.target.value)}
                        placeholder="Optional manual translation for the EN site. Leave empty for auto-translation."
                        className="input font-mono text-xs"
                        data-testid={`request-translation-en-${r.id}`}
                      />
                    </div>
                  </div>
                )}

                {r.status === "pending" && (
                  <div className="mt-4 flex gap-2">
                    <button
                      onClick={() => approve(r.id, r.type)}
                      disabled={busy === r.id}
                      className="btn btn-accent !py-2 !px-4 text-xs flex items-center gap-2"
                      data-testid={`request-approve-${r.id}`}
                    >
                      <Check size={12} /> Одобри
                    </button>
                    <button
                      onClick={() => reject(r.id)}
                      disabled={busy === r.id}
                      className="btn btn-secondary !py-2 !px-4 text-xs flex items-center gap-2 !border-[hsl(var(--danger))] !text-[hsl(var(--danger))]"
                      data-testid={`request-reject-${r.id}`}
                    >
                      <X size={12} /> Откажи
                    </button>
                  </div>
                )}
                {r.status !== "pending" && r.decision_reason && (
                  <div className="mt-3 text-xs text-[hsl(var(--ink-muted))]"><strong>Решение:</strong> {r.decision_reason}</div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
