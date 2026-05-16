import React, { useEffect, useState, useCallback } from "react";
import { CheckCircle2, AlertCircle, XCircle, RefreshCw, Activity, HelpCircle, Image as ImageIcon, Globe } from "lucide-react";
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
  // Image-queue + CDN are loaded by their own hooks (slower endpoints —
  // we don't want them blocking the main health refresh, and CDN probes
  // hit live Cloudflare so we throttle them to manual refresh only).
  const [imgQueue, setImgQueue] = useState(null);
  const [imgQueueErr, setImgQueueErr] = useState(null);
  const [cdn, setCdn] = useState(null);
  const [cdnLoading, setCdnLoading] = useState(false);
  const [cdnErr, setCdnErr] = useState(null);
  const [retryBusy, setRetryBusy] = useState(null);
  const [backfillBusy, setBackfillBusy] = useState(false);
  const [backfillResult, setBackfillResult] = useState(null);

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

  const loadImgQueue = useCallback(async () => {
    setImgQueueErr(null);
    try {
      const { data: payload } = await api.get("/admin/image-queue");
      setImgQueue(payload);
    } catch (e) {
      setImgQueueErr(e?.response?.data?.detail || e?.message || "Грешка");
    }
  }, []);

  const probeCdn = useCallback(async () => {
    setCdnLoading(true);
    setCdnErr(null);
    try {
      const { data: payload } = await api.get("/admin/cdn-health");
      setCdn(payload);
    } catch (e) {
      setCdnErr(e?.response?.data?.detail || e?.message || "Грешка");
    } finally {
      setCdnLoading(false);
    }
  }, []);

  const retryImage = useCallback(async (sha, auction_id) => {
    setRetryBusy(sha);
    try {
      await api.post("/admin/image-queue/retry", { sha, auction_id });
      await loadImgQueue();
    } catch (e) {
      setImgQueueErr(e?.response?.data?.detail || e?.message || "Грешка");
    } finally {
      setRetryBusy(null);
    }
  }, [loadImgQueue]);

  // Reverse-engineer status for legacy auctions whose images were
  // uploaded before the queue tracking existed. Idempotent — running
  // it twice is safe (no new work the second time).
  const runBackfill = useCallback(async () => {
    setBackfillBusy(true);
    setBackfillResult(null);
    try {
      const { data } = await api.post("/admin/image-queue/backfill");
      setBackfillResult(data);
      await loadImgQueue();
    } catch (e) {
      setImgQueueErr(e?.response?.data?.detail || e?.message || "Грешка");
    } finally {
      setBackfillBusy(false);
    }
  }, [loadImgQueue]);

  useEffect(() => { load(); loadImgQueue(); }, [load, loadImgQueue]);

  // Auto refresh every 10 seconds when toggled on.
  useEffect(() => {
    if (!auto) return;
    const id = setInterval(() => { load(); loadImgQueue(); }, 10000);
    return () => clearInterval(id);
  }, [auto, load, loadImgQueue]);

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

      {/* ── Image optimization queue ─────────────────────────────────── */}
      <div className="pt-6 border-t border-[hsl(var(--line))]">
        <div className="flex items-center gap-3 mb-3 flex-wrap">
          <ImageIcon size={18} className="text-[hsl(var(--accent))]" />
          <h2 className="text-lg font-semibold">Опашка за обработка на изображения</h2>
          <button
            onClick={loadImgQueue}
            className="btn btn-secondary !py-1 !px-2.5 text-[11px] flex items-center gap-1"
            data-testid="img-queue-refresh"
          ><RefreshCw size={11} /> Обнови</button>
          <button
            onClick={runBackfill}
            disabled={backfillBusy}
            className="btn btn-secondary !py-1 !px-2.5 text-[11px] flex items-center gap-1 disabled:opacity-50"
            data-testid="img-queue-backfill"
            title="Сканира всички обяви, открива вече-съществуващи variants на диска и маркира статуса"
          >
            <RefreshCw size={11} className={backfillBusy ? "animate-spin" : ""} />
            {backfillBusy ? "Сканиране…" : "Backfill статуси"}
          </button>
        </div>

        {/* Diagnostics strip — surfaces init / config issues. The dashboard
            shows 0 across the board WITHOUT this strip would be impossible
            to debug remotely. */}
        {imgQueue?.queue && (
          <div className="mb-3 p-2.5 rounded-card border border-[hsl(var(--line))] bg-[hsl(var(--surface))] text-[11px] font-mono flex flex-wrap gap-x-4 gap-y-1" data-testid="img-queue-diagnostics">
            <span>
              init:&nbsp;<span className={imgQueue.queue.initialized ? "text-emerald-600 font-semibold" : "text-red-500 font-semibold"}>
                {String(imgQueue.queue.initialized)}
              </span>
            </span>
            <span>
              worker:&nbsp;<span className={imgQueue.queue.worker_started ? "text-emerald-600" : "text-[hsl(var(--ink-muted))]"}>
                {String(imgQueue.queue.worker_started)}
              </span>
            </span>
            <span>
              upload_dir:&nbsp;<span className={imgQueue.queue.upload_dir_exists && imgQueue.queue.upload_dir_writable ? "text-emerald-600" : "text-red-500"}>
                {imgQueue.queue.upload_dir}
                {!imgQueue.queue.upload_dir_exists && " (НЕ СЪЩЕСТВУВА)"}
                {imgQueue.queue.upload_dir_exists && !imgQueue.queue.upload_dir_writable && " (read-only)"}
              </span>
            </span>
            <span>max_concurrency: {imgQueue.queue.max_concurrency}</span>
            <span>encode_timeout: {imgQueue.queue.encode_timeout_seconds}s</span>
          </div>
        )}

        {/* Backfill result toast */}
        {backfillResult && (
          <div className="mb-3 p-3 rounded-card border border-emerald-500/30 bg-emerald-500/10 text-sm" data-testid="img-queue-backfill-result">
            <div className="font-semibold mb-1">Backfill завърши</div>
            <div className="font-mono text-xs space-y-0.5">
              <div>Сканирани обяви: {backfillResult.auctions_scanned}</div>
              <div>Маркирани като оптимизирани: <span className="text-emerald-700 font-semibold">{backfillResult.marked_optimized}</span></div>
              <div>Поставени в опашка за нова обработка: <span className="text-amber-700 font-semibold">{backfillResult.enqueued}</span></div>
              <div>Вече следени (skip): {backfillResult.already_tracked}</div>
              {backfillResult.missing_originals > 0 && (
                <div className="text-red-500">Липсващи оригинали на диска: {backfillResult.missing_originals}</div>
              )}
              {backfillResult.errors?.length > 0 && (
                <div className="text-red-500">Грешки: {backfillResult.errors.length}</div>
              )}
            </div>
          </div>
        )}

        {/* Recent errors — surfaces "file missing on disk" / "auction not found"
            without forcing a journalctl trip. Cleared on backend restart. */}
        {imgQueue?.queue?.recent_errors?.length > 0 && (
          <div className="mb-3 p-3 rounded-card border border-amber-500/30 bg-amber-500/5" data-testid="img-queue-recent-errors">
            <div className="text-xs font-semibold text-amber-800 mb-1.5">
              Скорошни грешки в опашката ({imgQueue.queue.recent_errors.length})
            </div>
            <div className="font-mono text-[10px] space-y-0.5 max-h-32 overflow-y-auto">
              {imgQueue.queue.recent_errors.slice(-5).reverse().map((e, i) => (
                <div key={i} className="text-amber-900">
                  <span className="text-[hsl(var(--ink-muted))]">[{e.stage}]</span> {e.message}
                  {e.sha && <span className="text-[hsl(var(--ink-muted))]"> · sha={e.sha.slice(0, 10)}</span>}
                </div>
              ))}
            </div>
          </div>
        )}
        {imgQueueErr && (
          <div className="p-3 rounded-card border border-red-500/30 bg-red-500/10 text-sm text-red-500" data-testid="img-queue-error">
            {imgQueueErr}
          </div>
        )}
        {imgQueue && (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3" data-testid="img-queue-stats">
            <StatCard label="Опашка" value={imgQueue.queue?.pending} />
            <StatCard label="В работа" value={imgQueue.queue?.in_flight} />
            <StatCard label="Оптимизирани" value={imgQueue.db?.optimized} good />
            <StatCard label="Обработват се" value={imgQueue.db?.optimizing} />
            <StatCard label="Неуспешни" value={imgQueue.db?.failed} bad={imgQueue.db?.failed > 0} />
            <StatCard label="Оригинал само" value={imgQueue.db?.original_uploaded} />
          </div>
        )}

        {imgQueue?.failed?.length > 0 && (
          <div className="mt-4">
            <div className="text-sm font-semibold mb-2">
              Неуспешни оптимизации ({imgQueue.failed.length}{imgQueue.failed.length >= 50 && "+"})
            </div>
            <div className="border border-[hsl(var(--line))] rounded-card overflow-hidden">
              {imgQueue.failed.map((row) => (
                <div key={row.auction_id} className="border-b border-[hsl(var(--line))] last:border-b-0 p-3 bg-[hsl(var(--surface))]" data-testid={`img-failed-${row.auction_id}`}>
                  <div className="flex items-center justify-between gap-2 mb-2 flex-wrap">
                    <a href={`/auctions/${row.auction_id}`} className="text-sm font-medium hover:underline truncate">
                      {row.title || row.auction_id}
                    </a>
                    <span className="text-[10px] font-mono text-[hsl(var(--ink-muted))]">
                      {row.status} · {row.failed_images.length} fail
                    </span>
                  </div>
                  <div className="space-y-1.5">
                    {row.failed_images.map((img) => (
                      <div key={img.sha} className="flex items-center justify-between gap-2 text-xs">
                        <div className="flex-1 min-w-0">
                          <span className="font-mono text-[hsl(var(--ink-muted))]">{img.sha.slice(0, 10)}…</span>
                          {img.last_error && (
                            <span className="ml-2 text-red-500/80 truncate inline-block max-w-[400px] align-middle">
                              {img.last_error}
                            </span>
                          )}
                          {img.attempts != null && <span className="ml-2 text-[10px] text-[hsl(var(--ink-muted))]">опити: {img.attempts}</span>}
                        </div>
                        <button
                          onClick={() => retryImage(img.sha, row.auction_id)}
                          disabled={retryBusy === img.sha}
                          className="btn btn-secondary !py-1 !px-2 text-[11px] disabled:opacity-50"
                          data-testid={`img-retry-${img.sha.slice(0, 10)}`}
                        >{retryBusy === img.sha ? "…" : "Опитай отново"}</button>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* ── CDN health probe ─────────────────────────────────────────── */}
      <div className="pt-6 border-t border-[hsl(var(--line))]">
        <div className="flex items-center gap-3 mb-3">
          <Globe size={18} className="text-[hsl(var(--accent))]" />
          <h2 className="text-lg font-semibold">CDN probe (img.autoandbid.bg)</h2>
          <button
            onClick={probeCdn}
            disabled={cdnLoading}
            className="btn btn-secondary !py-1 !px-2.5 text-[11px] flex items-center gap-1 disabled:opacity-50"
            data-testid="cdn-probe-btn"
          ><RefreshCw size={11} className={cdnLoading ? "animate-spin" : ""} /> Пусни probe</button>
        </div>
        {cdnErr && (
          <div className="p-3 rounded-card border border-red-500/30 bg-red-500/10 text-sm text-red-500" data-testid="cdn-error">
            {cdnErr}
          </div>
        )}
        {cdn && (
          <div className="space-y-3" data-testid="cdn-result">
            <div className="text-xs text-[hsl(var(--ink-muted))] font-mono">
              Host: <span className="text-[hsl(var(--ink))]">{cdn.cdn_host}</span> ·
              {" "}Probe URL: <span className="text-[hsl(var(--ink))]">{cdn.probe_url}</span>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <CdnProbeCard title="Чрез Cloudflare" probe={cdn.cf_path} testid="cdn-cf" />
              <CdnProbeCard title="Директно към origin" probe={cdn.origin_path} testid="cdn-origin" />
            </div>
            {cdn.diagnosis && (
              <div className={`p-3 rounded-card border text-sm ${
                cdn.cf_path?.ok && cdn.origin_path?.ok
                  ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700"
                  : "border-amber-500/30 bg-amber-500/10 text-amber-800"
              }`} data-testid="cdn-diagnosis">
                <span className="font-semibold">Диагноза: </span>{cdn.diagnosis}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function StatCard({ label, value, good, bad }) {
  return (
    <div className={`p-3 rounded-card border bg-[hsl(var(--surface))] ${
      bad ? "border-red-500/40" : good ? "border-emerald-500/30" : "border-[hsl(var(--line))]"
    }`}>
      <div className="text-[10px] uppercase tracking-wider text-[hsl(var(--ink-muted))] mb-1">{label}</div>
      <div className={`text-2xl font-mono font-bold ${
        bad ? "text-red-500" : good ? "text-emerald-600" : "text-[hsl(var(--ink))]"
      }`}>{value ?? 0}</div>
    </div>
  );
}

function CdnProbeCard({ title, probe, testid }) {
  if (!probe) return null;
  const ok = probe.ok;
  return (
    <div className={`p-3 rounded-card border bg-[hsl(var(--surface))] ${ok ? "border-emerald-500/30" : "border-red-500/30"}`} data-testid={testid}>
      <div className="flex items-center justify-between mb-2">
        <div className="text-sm font-semibold">{title}</div>
        <StatusPill status={ok ? "ok" : "error"} />
      </div>
      <div className="text-xs font-mono space-y-1">
        {probe.error && <div className="text-red-500 break-all">{probe.error}</div>}
        {probe.status != null && <div>HTTP <span className="text-[hsl(var(--ink))] font-semibold">{probe.status}</span></div>}
        {probe.content_type && <div>Content-Type: <span className={probe.content_type.startsWith("image/") ? "text-emerald-600" : "text-red-500"}>{probe.content_type}</span></div>}
        {probe.location && <div className="break-all">Location: <span className={probe.wrong_redirect ? "text-red-500" : "text-[hsl(var(--ink))]"}>{probe.location}</span></div>}
        {probe.server && <div>Server: <span className="text-[hsl(var(--ink))]">{probe.server}</span></div>}
        {probe.cf_ray && <div>CF-Ray: <span className="text-[hsl(var(--ink))]">{probe.cf_ray}</span></div>}
      </div>
    </div>
  );
}
