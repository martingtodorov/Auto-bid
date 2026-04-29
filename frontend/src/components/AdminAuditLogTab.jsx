import React, { useEffect, useState } from "react";
import { ScrollText, Filter, RefreshCw, Download, Trash2, Calendar, X } from "lucide-react";
import { api, API_BASE } from "../lib/apiClient";
import { useAuth, formatError } from "../lib/auth";

const ACTION_LABELS = {
  "settings.update": "Обнови настройки",
  "stripe.update": "Stripe конфигурация",
  "user.ban": "Блокиране на потребител",
  "comment.delete": "Изтриване на коментар",
  "auction.reactivate": "Реактивиране на обява",
  "audit_log.export": "Експорт на журнал",
  "audit_log.purge": "Изчистване на журнал",
  "audit_log.delete_one": "Изтриване на запис",
};

export default function AdminAuditLogTab() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [actionFilter, setActionFilter] = useState("");
  const [offset, setOffset] = useState(0);
  const [showPurge, setShowPurge] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const LIMIT = 50;

  const load = async () => {
    setLoading(true);
    setErr("");
    const params = { limit: LIMIT, offset };
    if (actionFilter) params.action = actionFilter;
    try {
      const { data } = await api.get("/admin/audit-log", { params });
      setItems(data.items || []); setTotal(data.total || 0);
    } catch (e) { setItems([]); setTotal(0); setErr(formatError(e)); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [actionFilter, offset]);

  // Запазваме CSV като file download.  Fetch с включени credentials, за
  // да минат auth cookies; CSRF не е нужен на GET.
  const exportCSV = async () => {
    setErr(""); setBusy(true);
    try {
      const params = new URLSearchParams();
      if (actionFilter) params.set("action", actionFilter);
      const res = await fetch(`${API_BASE}/admin/audit-log/export${params.toString() ? "?" + params : ""}`, {
        credentials: "include",
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `audit_log_${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "")}.csv`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
    } catch (e) { setErr(formatError(e)); }
    finally { setBusy(false); }
  };

  const deleteOne = async (id) => {
    if (!window.confirm("Сигурен ли сте, че искате да изтриете този запис?")) return;
    setBusy(true);
    try {
      await api.delete(`/admin/audit-log/${id}`);
      await load();
    } catch (e) { setErr(formatError(e)); }
    finally { setBusy(false); }
  };

  return (
    <div className="mt-10" data-testid="admin-audit-tab">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3">
          <ScrollText size={18} className="text-[hsl(var(--accent))]" />
          <h2 className="font-serif text-2xl">Журнал на действията</h2>
          <span className="text-sm text-[hsl(var(--ink-muted))]">({total})</span>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <div className="relative">
            <Filter size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[hsl(var(--ink-muted))]" />
            <select value={actionFilter} onChange={(e) => { setOffset(0); setActionFilter(e.target.value); }} className="border border-[hsl(var(--line))] rounded-card pl-9 pr-3 py-2 bg-white text-sm" data-testid="audit-action-filter">
              <option value="">Всички действия</option>
              {Object.entries(ACTION_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </div>
          <button onClick={load} disabled={busy} className="p-2 rounded-card border border-[hsl(var(--line))] bg-white hover:bg-[hsl(var(--surface))] disabled:opacity-50" data-testid="audit-refresh" title="Опресни">
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          </button>
          <button onClick={exportCSV} disabled={busy || items.length === 0} className="px-3 py-2 rounded-card border border-[hsl(var(--line))] bg-white hover:bg-[hsl(var(--surface))] disabled:opacity-50 text-sm inline-flex items-center gap-1.5" data-testid="audit-export-csv">
            <Download size={13} /> CSV
          </button>
          {isAdmin && (
            <button onClick={() => setShowPurge(true)} disabled={busy} className="px-3 py-2 rounded-card border border-[hsl(var(--danger))]/40 text-[hsl(var(--danger))] hover:bg-[hsl(var(--danger))]/5 disabled:opacity-50 text-sm inline-flex items-center gap-1.5" data-testid="audit-purge-open">
              <Trash2 size={13} /> Изчисти
            </button>
          )}
        </div>
      </div>

      {err && <p className="mt-3 text-sm text-[hsl(var(--danger))]" data-testid="audit-error">{err}</p>}

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
                {isAdmin && <th className="p-3 w-10" aria-label="Действия" />}
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
                  {isAdmin && (
                    <td className="p-2">
                      <button
                        onClick={() => deleteOne(e.id)}
                        disabled={busy}
                        className="p-1.5 rounded-card hover:bg-[hsl(var(--danger))]/10 text-[hsl(var(--ink-muted))] hover:text-[hsl(var(--danger))] disabled:opacity-50"
                        title="Изтрий този запис"
                        data-testid={`audit-delete-${e.id}`}
                      >
                        <Trash2 size={13} />
                      </button>
                    </td>
                  )}
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

      {showPurge && <PurgeModal onClose={() => setShowPurge(false)} onDone={async () => { setShowPurge(false); await load(); }} actionFilter={actionFilter} />}
    </div>
  );
}

function PurgeModal({ onClose, onDone, actionFilter }) {
  // Default: всичко по-старо от 90 дни
  const ninetyDaysAgo = new Date(Date.now() - 90 * 24 * 60 * 60 * 1000);
  const [before, setBefore] = useState(ninetyDaysAgo.toISOString().slice(0, 10));
  const [action, setAction] = useState(actionFilter || "");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const submit = async () => {
    setErr("");
    if (confirm !== "DELETE") {
      setErr('Въведете "DELETE" за потвърждение');
      return;
    }
    if (!before && !action) {
      setErr("Поне един филтър е задължителен (дата или действие).");
      return;
    }
    setBusy(true);
    try {
      const params = { confirm: "DELETE" };
      if (before) params.before = `${before}T23:59:59Z`;
      if (action) params.action = action;
      const { data } = await api.delete("/admin/audit-log", { params });
      window.alert(`Изтрити ${data.deleted || 0} записа.`);
      onDone();
    } catch (e) { setErr(formatError(e)); }
    finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-[60] bg-black/50 backdrop-blur-sm flex items-center justify-center p-4" data-testid="audit-purge-modal">
      <div className="bg-white rounded-card w-full max-w-md shadow-xl">
        <div className="flex items-center justify-between px-5 py-4 border-b border-[hsl(var(--line))]">
          <div className="flex items-center gap-2 text-[hsl(var(--danger))]">
            <Trash2 size={16} />
            <h3 className="font-serif text-lg">Изчистване на журнал</h3>
          </div>
          <button onClick={onClose} disabled={busy}><X size={18} /></button>
        </div>
        <div className="p-5 space-y-4">
          <p className="text-sm text-[hsl(var(--ink-muted))]">
            Тази операция е необратима. Изтриването ще се впише като нов запис в журнала за проследимост.
          </p>
          <div>
            <label className="overline text-[hsl(var(--ink-muted))] mb-1.5 flex items-center gap-1.5"><Calendar size={11} /> Изтрий записи преди</label>
            <input type="date" value={before} onChange={(e) => setBefore(e.target.value)} className="w-full border border-[hsl(var(--line))] h-11 px-3 text-sm" data-testid="audit-purge-before" />
          </div>
          <div>
            <label className="overline text-[hsl(var(--ink-muted))] mb-1.5 block">Само определено действие (по избор)</label>
            <select value={action} onChange={(e) => setAction(e.target.value)} className="w-full border border-[hsl(var(--line))] h-11 px-3 text-sm bg-white" data-testid="audit-purge-action">
              <option value="">Всички действия</option>
              {Object.entries(ACTION_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </div>
          <div>
            <label className="overline text-[hsl(var(--ink-muted))] mb-1.5 block">Напишете <span className="font-mono">DELETE</span> за потвърждение</label>
            <input type="text" value={confirm} onChange={(e) => setConfirm(e.target.value)} placeholder="DELETE" className="w-full border border-[hsl(var(--danger))]/30 h-11 px-3 text-sm font-mono" data-testid="audit-purge-confirm" />
          </div>
          {err && <p className="text-sm text-[hsl(var(--danger))]">{err}</p>}
          <div className="flex items-center justify-end gap-2 pt-2">
            <button onClick={onClose} disabled={busy} className="btn btn-secondary">Отказ</button>
            <button onClick={submit} disabled={busy || confirm !== "DELETE"} className="btn !bg-[hsl(var(--danger))] !text-white !border-[hsl(var(--danger))] inline-flex items-center gap-2 disabled:opacity-50" data-testid="audit-purge-submit">
              <Trash2 size={13} /> {busy ? "Изтриване…" : "Изтрий записите"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
