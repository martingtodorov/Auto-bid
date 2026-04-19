import React, { useEffect, useState } from "react";
import { ScrollText, Filter, RefreshCw } from "lucide-react";
import { api } from "../lib/apiClient";

const ACTION_LABELS = {
  "settings.update": "Обнови настройки",
  "stripe.update": "Stripe конфигурация",
  "user.ban": "Блокиране на потребител",
  "comment.delete": "Изтриване на коментар",
  "auction.reactivate": "Реактивиране на обява",
};

export default function AdminAuditLogTab() {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [actionFilter, setActionFilter] = useState("");
  const [offset, setOffset] = useState(0);
  const LIMIT = 50;

  const load = async () => {
    setLoading(true);
    const params = { limit: LIMIT, offset };
    if (actionFilter) params.action = actionFilter;
    try {
      const { data } = await api.get("/admin/audit-log", { params });
      setItems(data.items || []); setTotal(data.total || 0);
    } catch (e) { setItems([]); setTotal(0); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [actionFilter, offset]);

  return (
    <div className="mt-10" data-testid="admin-audit-tab">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3">
          <ScrollText size={18} className="text-[hsl(var(--accent))]" />
          <h2 className="font-serif text-2xl">Журнал на действията</h2>
          <span className="text-sm text-[hsl(var(--ink-muted))]">({total})</span>
        </div>
        <div className="flex items-center gap-3">
          <div className="relative">
            <Filter size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[hsl(var(--ink-muted))]" />
            <select value={actionFilter} onChange={(e) => { setOffset(0); setActionFilter(e.target.value); }} className="border border-[hsl(var(--line))] rounded-card pl-9 pr-3 py-2 bg-white text-sm" data-testid="audit-action-filter">
              <option value="">Всички действия</option>
              {Object.entries(ACTION_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </div>
          <button onClick={load} className="p-2 rounded-card border border-[hsl(var(--line))] bg-white hover:bg-[hsl(var(--surface))]" data-testid="audit-refresh">
            <RefreshCw size={14} />
          </button>
        </div>
      </div>

      <div className="mt-6 rounded-card border border-[hsl(var(--line))] bg-white overflow-hidden">
        {loading ? (
          <div className="py-16 text-center text-sm text-[hsl(var(--ink-muted))]">Зареждане…</div>
        ) : items.length === 0 ? (
          <div className="py-16 text-center text-sm text-[hsl(var(--ink-muted))]" data-testid="audit-empty">Няма записи в журнала.</div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-[hsl(var(--surface))] text-xs uppercase text-[hsl(var(--ink-muted))]">
              <tr>
                <th className="text-left p-3">Време</th>
                <th className="text-left p-3">Действие</th>
                <th className="text-left p-3">Изпълнител</th>
                <th className="text-left p-3">Обект</th>
                <th className="text-left p-3">Детайли</th>
                <th className="text-left p-3">IP</th>
              </tr>
            </thead>
            <tbody data-testid="audit-list">
              {items.map((e) => (
                <tr key={e.id} className="border-t border-[hsl(var(--line))]" data-testid={`audit-row-${e.id}`}>
                  <td className="p-3 font-mono text-xs text-[hsl(var(--ink-muted))] whitespace-nowrap">{new Date(e.at).toLocaleString("bg-BG", { dateStyle: "short", timeStyle: "medium" })}</td>
                  <td className="p-3 font-medium">{ACTION_LABELS[e.action] || e.action}</td>
                  <td className="p-3">
                    <div className="font-medium">{e.actor_email || "—"}</div>
                    <div className="text-xs text-[hsl(var(--ink-muted))]">{e.actor_role}</div>
                  </td>
                  <td className="p-3 font-mono text-xs">{e.target_type}{e.target_id ? `/${e.target_id.slice(0, 8)}…` : ""}</td>
                  <td className="p-3 text-xs text-[hsl(var(--ink-muted))] max-w-[280px] truncate">
                    {e.details && Object.keys(e.details).length > 0 ? JSON.stringify(e.details) : "—"}
                  </td>
                  <td className="p-3 text-xs font-mono text-[hsl(var(--ink-muted))]">{e.ip || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {total > LIMIT && (
        <div className="mt-4 flex items-center justify-between" data-testid="audit-pagination">
          <span className="text-sm text-[hsl(var(--ink-muted))]">{offset + 1}–{Math.min(offset + items.length, total)} от {total}</span>
          <div className="flex gap-2">
            <button disabled={offset === 0} onClick={() => setOffset((o) => Math.max(0, o - LIMIT))} className="px-3 py-1.5 border border-[hsl(var(--line))] rounded-card text-sm bg-white disabled:opacity-40">Предишна</button>
            <button disabled={offset + LIMIT >= total} onClick={() => setOffset((o) => o + LIMIT)} className="px-3 py-1.5 border border-[hsl(var(--line))] rounded-card text-sm bg-white disabled:opacity-40">Следваща</button>
          </div>
        </div>
      )}
    </div>
  );
}
