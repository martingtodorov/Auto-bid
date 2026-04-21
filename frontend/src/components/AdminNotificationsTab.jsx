import React, { useEffect, useState, useCallback } from "react";
import { Mail, CheckCircle2, XCircle, Clock, RefreshCw } from "lucide-react";
import { api } from "../lib/apiClient";
import { formatError } from "../lib/auth";

const STATUS_META = {
  sent: { label: "Изпратен", icon: CheckCircle2, cls: "text-[hsl(var(--success))] border-[hsl(var(--success))]/40" },
  failed: { label: "Грешка", icon: XCircle, cls: "text-[hsl(var(--danger))] border-[hsl(var(--danger))]/40" },
  queued: { label: "Чака", icon: Clock, cls: "text-[hsl(var(--ink-muted))] border-[hsl(var(--line))]" },
};

export default function AdminNotificationsTab() {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setErr("");
    try {
      const params = { limit: 200 };
      if (status) params.status = status;
      const { data } = await api.get("/admin/notifications", { params });
      setItems(data.items || []);
      setTotal(data.total || 0);
    } catch (e) { setErr(formatError(e)); }
    finally { setLoading(false); }
  }, [status]);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="mt-10 space-y-5" data-testid="admin-notifications-tab">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <div className="overline text-[hsl(var(--accent))]">Комуникация</div>
          <h2 className="font-serif text-3xl">Дневник на известията</h2>
          <p className="mt-2 text-sm text-[hsl(var(--ink-muted))]">Всички имейли, изпратени от платформата ({total} общо).</p>
        </div>
        <div className="flex gap-2 items-center">
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            className="input !w-auto"
            data-testid="notifications-status-filter"
          >
            <option value="">Всички статуси</option>
            <option value="sent">Изпратени</option>
            <option value="failed">Грешка</option>
            <option value="queued">Чакащи</option>
          </select>
          <button onClick={load} className="btn btn-primary !py-2 !px-4 flex items-center gap-2" data-testid="notifications-refresh">
            <RefreshCw size={14} /> Опресни
          </button>
        </div>
      </div>

      {err && <p className="text-sm text-[hsl(var(--danger))]" data-testid="notifications-error">{err}</p>}

      {loading ? (
        <div className="py-24 text-center text-[hsl(var(--ink-muted))]">Зареждане…</div>
      ) : items.length === 0 ? (
        <div className="py-24 text-center rounded-card border border-[hsl(var(--line))]" data-testid="notifications-empty">
          <Mail size={32} className="mx-auto text-[hsl(var(--ink-muted))]" />
          <p className="mt-4 font-serif text-2xl">Няма записи</p>
          <p className="mt-2 text-sm text-[hsl(var(--ink-muted))]">Когато платформата изпрати имейл, той ще се появи тук.</p>
        </div>
      ) : (
        <div className="rounded-card border border-[hsl(var(--line))] overflow-hidden bg-white" data-testid="notifications-list">
          <div className="hidden md:grid grid-cols-[1fr_1.2fr_1.8fr_0.8fr_0.9fr] gap-3 px-5 py-3 rule-b bg-[hsl(var(--surface))] overline text-[hsl(var(--ink-muted))]">
            <span>Кога</span>
            <span>Получател</span>
            <span>Тема</span>
            <span>Статус</span>
            <span>Тип</span>
          </div>
          {items.map((n, idx) => {
            const meta = STATUS_META[n.status] || STATUS_META.queued;
            const Icon = meta.icon;
            return (
              <div
                key={n.id || idx}
                className="grid grid-cols-1 md:grid-cols-[1fr_1.2fr_1.8fr_0.8fr_0.9fr] gap-3 items-center p-4 rule-b last:border-b-0 text-sm"
                data-testid={`notif-row-${idx}`}
              >
                <div className="text-xs font-mono text-[hsl(var(--ink-muted))]">
                  {n.at ? new Date(n.at).toLocaleString("bg-BG") : "—"}
                </div>
                <div className="font-mono text-xs truncate" title={n.to || ""}>{n.to || "—"}</div>
                <div className="truncate" title={n.subject || ""}>{n.subject || "—"}</div>
                <div>
                  <span className={`pill text-xs ${meta.cls}`}>
                    <Icon size={11} /> {meta.label}
                  </span>
                </div>
                <div className="text-xs text-[hsl(var(--ink-muted))]">{n.template_key || n.type || "manual"}</div>
              </div>
            );
          })}
        </div>
      )}

      {/* CSV Export */}
      <section className="mt-8 rounded-card border border-[hsl(var(--line))] bg-white p-6" data-testid="transactions-export-section">
        <h3 className="font-serif text-2xl">Експорт на транзакции</h3>
        <p className="mt-2 text-sm text-[hsl(var(--ink-muted))]">
          Сваля всички продадени обяви като CSV — включва цена, такса на купувача, продавач и купувач.
        </p>
        <a
          href={`${process.env.REACT_APP_BACKEND_URL}/api/admin/transactions/export.csv`}
          download
          className="btn btn-primary !py-2 !px-5 inline-flex items-center gap-2 mt-4"
          data-testid="transactions-export-btn"
        >
          <Mail size={14} /> Изтегли CSV
        </a>
        <p className="mt-3 text-xs text-[hsl(var(--ink-muted))]">
          Забележка: ще бъдете пренасочени към backend endpoint. Ако не се изтегли автоматично, копирайте линка по-горе.
        </p>
      </section>
    </div>
  );
}
