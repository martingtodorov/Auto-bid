import React, { useEffect, useState, useCallback } from "react";
import { Archive, RefreshCw, Eye, Edit3, Mail, Gavel, Trash, RotateCcw } from "lucide-react";
import { api, formatEUR } from "../lib/apiClient";
import { formatError } from "../lib/auth";
import AdminBidHistoryModal from "./AdminBidHistoryModal";
import AdminEditModal from "./AdminEditModal";
import { auctionUrl } from "../lib/auctionUrl";
import { grossEUR } from "../lib/vat";

const STATUS_LABELS = {
  ended: "Приключил без продажба",
  reserve_not_met: "Резервът не е достигнат",
  cancelled: "Отказан",
  withdrawn: "Оттеглен",
};

/**
 * Admin tab — "Unsold" auctions.
 *
 * Lists auctions that have finalized without sale, grouped visually by status.
 * Provides one-click "Renew" (re-extend) action and a deep link to the high
 * bidder's email when there is one (so admins can follow up on
 * `reserve_not_met` cases by hand).
 */
export default function AdminUnsoldTab() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(null);
  const [bidsFor, setBidsFor] = useState(null);
  const [editingId, setEditingId] = useState(null);
  const [statusFilter, setStatusFilter] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setErr("");
    try {
      const { data } = await api.get("/admin/unsold");
      setItems(data || []);
    } catch (e) {
      setErr(formatError(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const renew = async (id, title) => {
    const daysStr = window.prompt(
      `Подновяване на „${title || id}". Колко дни да е отворена отново (1–60)?`,
      "10"
    );
    if (!daysStr) return;
    const days = parseInt(daysStr, 10);
    if (!Number.isInteger(days) || days < 1 || days > 60) {
      alert("Невалиден брой дни (1–60).");
      return;
    }
    setBusy(id);
    setErr("");
    try {
      const { data } = await api.post(`/admin/auctions/${id}/extend`, null, { params: { days } });
      alert(`Подновена. Нов край: ${new Date(data.ends_at).toLocaleString("bg-BG")}`);
      await load();
    } catch (e) {
      setErr(formatError(e));
    } finally {
      setBusy(null);
    }
  };

  const archive = async (id) => {
    if (!window.confirm("Архивирай обявата? (скрита от публичните листинги, всичко се запазва)")) return;
    setBusy(id);
    try {
      await api.post(`/admin/auctions/${id}/archive`);
      await load();
    } catch (e) {
      setErr(formatError(e));
    } finally {
      setBusy(null);
    }
  };

  const filtered = statusFilter
    ? items.filter((a) => a.status === statusFilter)
    : items;

  const counts = items.reduce((acc, a) => {
    acc[a.status] = (acc[a.status] || 0) + 1;
    return acc;
  }, {});

  return (
    <div className="mt-10" data-testid="admin-unsold-tab">
      <div className="flex items-center justify-between flex-wrap gap-4 mb-5">
        <div>
          <h2 className="font-serif text-2xl">Непродадени автомобили</h2>
          <p className="mt-1 text-sm text-[hsl(var(--ink-muted))]">
            Финализирани търгове, които не са завършили със сделка. Може да ги подновите или архивирате.
          </p>
        </div>
        <button onClick={load} className="btn btn-secondary !py-2 !px-4 text-sm flex items-center gap-2" data-testid="unsold-refresh">
          <RefreshCw size={14} /> Опресни
        </button>
      </div>

      {/* Status pills as filter */}
      <div className="flex flex-wrap gap-2 mb-5">
        <button
          onClick={() => setStatusFilter("")}
          className={`pill text-xs ${statusFilter === "" ? "pill-live" : ""}`}
          data-testid="unsold-filter-all"
        >
          Всички ({items.length})
        </button>
        {Object.entries(STATUS_LABELS).map(([k, label]) => (
          <button
            key={k}
            onClick={() => setStatusFilter(k)}
            className={`pill text-xs ${statusFilter === k ? "pill-live" : ""}`}
            data-testid={`unsold-filter-${k}`}
          >
            {label} ({counts[k] || 0})
          </button>
        ))}
      </div>

      {err && <p className="text-sm text-[hsl(var(--danger))] mb-3">{err}</p>}

      {loading ? (
        <div className="py-24 text-center text-sm text-[hsl(var(--ink-muted))]">Зареждане…</div>
      ) : filtered.length === 0 ? (
        <div className="py-24 text-center rounded-card border border-[hsl(var(--line))]">
          <Archive size={32} className="mx-auto text-[hsl(var(--ink-muted))]" />
          <p className="mt-4 font-serif text-2xl">Няма непродадени обяви</p>
          <p className="mt-2 text-sm text-[hsl(var(--ink-muted))]">Всичко е продадено или активно.</p>
        </div>
      ) : (
        <div className="rounded-card border border-[hsl(var(--line))] overflow-hidden bg-white" data-testid="unsold-list">
          <div className="hidden md:grid grid-cols-[1.6fr_0.9fr_0.8fr_1fr_1.3fr] gap-3 px-5 py-3 rule-b bg-[hsl(var(--surface))] overline text-[hsl(var(--ink-muted))]">
            <span>Обява</span>
            <span>Статус</span>
            <span>Текуща цена</span>
            <span>Топ наддавач</span>
            <span>Действия</span>
          </div>
          {filtered.map((a) => (
            <div
              key={a.id}
              className="grid grid-cols-1 md:grid-cols-[1.6fr_0.9fr_0.8fr_1fr_1.3fr] gap-3 items-center p-4 rule-b last:border-b-0"
              data-testid={`unsold-row-${a.id}`}
            >
              <div className="flex items-center gap-3 min-w-0">
                {a.images?.[0] ? (
                  <img src={a.thumbnails?.[0] || a.images[0]} className="w-14 h-10 object-cover rounded-md shrink-0" alt="" loading="lazy" />
                ) : (
                  <div className="w-14 h-10 bg-[hsl(var(--surface))] rounded-md shrink-0" />
                )}
                <div className="min-w-0">
                  <div className="font-semibold text-sm truncate">{a.title}</div>
                  <div className="text-xs text-[hsl(var(--ink-muted))]">
                    {a.make} · {a.year} · {a.bid_count || 0} бида
                  </div>
                </div>
              </div>
              <div>
                <span className="pill text-xs" data-testid={`unsold-status-${a.id}`}>
                  {STATUS_LABELS[a.status] || a.status}
                </span>
              </div>
              <div className="font-serif text-base">{formatEUR(grossEUR(a.current_bid_eur || 0, a))}</div>
              <div className="text-xs min-w-0">
                {a.high_bidder_name ? (
                  <>
                    <div className="truncate">{a.high_bidder_name}</div>
                    {a.high_bidder_email && (
                      <a
                        href={`mailto:${a.high_bidder_email}`}
                        className="text-[hsl(var(--accent))] hover:underline font-mono truncate inline-flex items-center gap-1"
                        data-testid={`unsold-bidder-email-${a.id}`}
                      >
                        <Mail size={11} /> {a.high_bidder_email}
                      </a>
                    )}
                  </>
                ) : (
                  <span className="text-[hsl(var(--ink-muted))]">—</span>
                )}
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  onClick={() => renew(a.id, a.title)}
                  disabled={busy === a.id}
                  className="btn btn-accent !py-1.5 !px-3 text-xs flex items-center gap-1"
                  data-testid={`unsold-renew-${a.id}`}
                >
                  <RefreshCw size={12} /> Поднови
                </button>
                <a
                  href={auctionUrl(a)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="btn btn-secondary !py-1.5 !px-3 text-xs flex items-center gap-1"
                  data-testid={`unsold-preview-${a.id}`}
                >
                  <Eye size={12} /> Преглед
                </a>
                <button
                  onClick={() => setEditingId(a.id)}
                  className="btn btn-secondary !py-1.5 !px-3 text-xs flex items-center gap-1"
                  data-testid={`unsold-edit-${a.id}`}
                >
                  <Edit3 size={12} /> Редактирай
                </button>
                <button
                  onClick={() => setBidsFor({ id: a.id, title: a.title })}
                  className="btn btn-secondary !py-1.5 !px-3 text-xs flex items-center gap-1"
                  data-testid={`unsold-bids-${a.id}`}
                >
                  <Gavel size={12} /> Бидове
                </button>
                <button
                  onClick={() => archive(a.id)}
                  disabled={busy === a.id}
                  className="btn btn-secondary !py-1.5 !px-3 text-xs flex items-center gap-1"
                  data-testid={`unsold-archive-${a.id}`}
                >
                  <Archive size={12} /> Архив
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {bidsFor && (
        <AdminBidHistoryModal
          auctionId={bidsFor.id}
          auctionTitle={bidsFor.title}
          onClose={() => setBidsFor(null)}
        />
      )}
      {editingId && (
        <AdminEditModal
          auctionId={editingId}
          onClose={() => setEditingId(null)}
          onSaved={() => { setEditingId(null); load(); }}
        />
      )}
    </div>
  );
}
