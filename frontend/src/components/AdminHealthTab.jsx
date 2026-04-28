import React, { useEffect, useState, useCallback } from "react";
import { CheckCircle2, AlertCircle, XCircle, RefreshCw, Activity, HelpCircle } from "lucide-react";
import { api } from "../lib/apiClient";

const STATUS_CFG = {
  ok:        { color: "text-emerald-500", bg: "bg-emerald-500/10",  border: "border-emerald-500/30", icon: CheckCircle2, label: "OK" },
  degraded:  { color: "text-amber-500",   bg: "bg-amber-500/10",    border: "border-amber-500/30",   icon: AlertCircle,  label: "DEGRADED" },
  error:     { color: "text-red-500",     bg: "bg-red-500/10",      border: "border-red-500/30",     icon: XCircle,      label: "ERROR" },
  unknown:   { color: "text-slate-400",   bg: "bg-slate-500/10",    border: "border-slate-500/30",   icon: HelpCircle,   label: "UNKNOWN" },
};

const SERVICE_LABELS = {
  mongo: "MongoDB",
  postgres: "PostgreSQL",
  outbox: "Outbox Worker",
  push: "Web Push",
  auctions: "Auctions",
};

const StatusPill = ({ status }) => {
  const cfg = STATUS_CFG[status] || STATUS_CFG.unknown;
  const Ico = cfg.icon;
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px] font-mono font-semibold border ${cfg.color} ${cfg.bg} ${cfg.border}`}>
      <Ico size={12} /> {cfg.label}
    </span>
  );
};

export default function AdminHealthTab() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [auto, setAuto] = useState(true);
  const [lastFetch, setLastFetch] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const t0 = performance.now();
      const { data: payload } = await api.get("/health");
      setData(payload);
      setLastFetch({ at: new Date(), rt: Math.round(performance.now() - t0) });
    } catch (e) {
      setError(e?.response?.data?.detail || e?.message || "Грешка");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Auto refresh every 10 seconds when toggled on.
  useEffect(() => {
    if (!auto) return;
    const id = setInterval(load, 10000);
    return () => clearInterval(id);
  }, [auto, load]);

  const overall = data?.status || "unknown";

  return (
    <div className="space-y-6" data-testid="admin-health-tab">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <Activity size={20} className="text-[hsl(var(--accent))]" />
          <h2 className="text-lg font-semibold">Системно здраве</h2>
          <StatusPill status={overall} />
        </div>
        <div className="flex items-center gap-3">
          <label className="text-xs flex items-center gap-1.5 cursor-pointer text-[hsl(var(--ink-muted))]">
            <input
              type="checkbox"
              checked={auto}
              onChange={(e) => setAuto(e.target.checked)}
              data-testid="health-auto-toggle"
            />
            Автоматичен преглед (10с)
          </label>
          <button
            onClick={load}
            disabled={loading}
            className="btn btn-secondary !py-1.5 !px-3 text-xs flex items-center gap-1.5 disabled:opacity-50"
            data-testid="health-refresh"
          >
            <RefreshCw size={12} className={loading ? "animate-spin" : ""} /> Обнови
          </button>
        </div>
      </div>

      {error && (
        <div className="p-3 rounded-card border border-red-500/30 bg-red-500/10 text-sm text-red-500" data-testid="health-error">
          {error}
        </div>
      )}

      {data && (
        <>
          <div className="text-[11px] text-[hsl(var(--ink-muted))] font-mono">
            Проверено: {new Date(data.checked_at).toLocaleString()} ·
            {" "}общо ~{data.total_latency_ms} ms
            {lastFetch && <> · клиент: {lastFetch.rt} ms</>}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4" data-testid="health-services-grid">
            {Object.entries(data.services || {}).map(([key, svc]) => {
              const cfg = STATUS_CFG[svc.status] || STATUS_CFG.unknown;
              const Ico = cfg.icon;
              return (
                <div
                  key={key}
                  className={`p-4 rounded-card border bg-[hsl(var(--surface))] ${cfg.border}`}
                  data-testid={`health-service-${key}`}
                >
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <Ico size={16} className={cfg.color} />
                      <h3 className="font-semibold text-sm">{SERVICE_LABELS[key] || key}</h3>
                    </div>
                    <StatusPill status={svc.status} />
                  </div>

                  <div className="text-xs text-[hsl(var(--ink-muted))] space-y-1 font-mono">
                    {svc.latency_ms != null && (
                      <div>Латентност: <span className="text-[hsl(var(--ink))]">{svc.latency_ms} ms</span></div>
                    )}
                    {svc.subscriptions != null && (
                      <div>Subscriptions: <span className="text-[hsl(var(--ink))]">{svc.subscriptions}</span></div>
                    )}
                    {svc.live != null && (
                      <div>Активни търгове: <span className="text-[hsl(var(--ink))]">{svc.live}</span></div>
                    )}
                    {svc.ending_within_1h != null && (
                      <div>Завършващи &lt; 1ч: <span className="text-[hsl(var(--ink))]">{svc.ending_within_1h}</span></div>
                    )}
                    {svc.pending != null && (
                      <div>Чакащи: <span className="text-[hsl(var(--ink))]">{svc.pending}</span></div>
                    )}
                    {svc.dead_letter != null && (
                      <div>
                        Dead letter: <span className={svc.dead_letter > 0 ? "text-red-500 font-semibold" : "text-[hsl(var(--ink))]"}>
                          {svc.dead_letter}
                        </span>
                      </div>
                    )}
                    {svc.error && (
                      <div className="text-red-500 break-all whitespace-pre-wrap" data-testid={`health-service-${key}-error`}>
                        {svc.error}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}

      {!data && !error && loading && (
        <div className="p-6 text-center text-sm text-[hsl(var(--ink-muted))]">Зареждане…</div>
      )}
    </div>
  );
}
