import React, { useEffect, useState, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { Archive, RotateCcw, Trash2, AlertTriangle, CheckSquare, Square } from "lucide-react";
import { api } from "../lib/apiClient";

/** Admin tab — manage soft-deleted (archived) auctions.
 *  Bulk restore + bulk hard-delete (with double confirmation).
 *  Hard-delete refuses non-archived rows server-side. */
export default function AdminArchiveTab() {
  const { t } = useTranslation();
  const [items, setItems] = useState([]);
  const [selected, setSelected] = useState(new Set());
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/admin/auctions/archived");
      setItems(data || []);
      setSelected(new Set());
    } catch (e) {
      setErr(e?.response?.data?.detail || String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const toggle = (id) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id); else next.add(id);
    setSelected(next);
  };
  const toggleAll = () => {
    if (selected.size === items.length) setSelected(new Set());
    else setSelected(new Set(items.map((a) => a.id)));
  };

  const bulkRestore = async () => {
    if (selected.size === 0) return;
    setBusy(true); setErr(""); setMsg("");
    try {
      const { data } = await api.post("/admin/auctions/bulk-restore", { ids: [...selected] });
      setMsg(t("admin.archive.restored_count", { count: data.restored.length }));
      await load();
    } catch (e) {
      setErr(e?.response?.data?.detail || String(e));
    } finally {
      setBusy(false);
    }
  };

  const bulkDelete = async () => {
    if (selected.size === 0) return;
    const word = t("admin.archive.confirm_word", "ИЗТРИЙ");
    const conf = window.prompt(
      t("admin.archive.confirm_delete", { count: selected.size, word }),
    );
    if (conf !== word) return;
    setBusy(true); setErr(""); setMsg("");
    try {
      const { data } = await api.post("/admin/auctions/bulk-delete", { ids: [...selected] });
      setMsg(t("admin.archive.deleted_count", { count: data.deleted.length }));
      await load();
    } catch (e) {
      setErr(e?.response?.data?.detail || String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-10" data-testid="admin-archive-tab">
      <div className="flex items-start justify-between flex-wrap gap-4 mb-6">
        <div>
          <div className="overline text-[hsl(var(--ink-muted))]"><Archive size={12} className="inline" /> {t("admin.archive.overline", "Архив")}</div>
          <h2 className="font-serif text-2xl lg:text-3xl mt-1.5">{t("admin.archive.title", "Архивирани обяви")}</h2>
          <p className="text-sm text-[hsl(var(--ink-muted))] mt-2 max-w-xl">
            {t("admin.archive.subtitle", "Тук са обявите, които са скрити от публичните листинги. Снимки, наддавания и коментари са запазени и могат да се възстановят.")}
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <button
            onClick={bulkRestore}
            disabled={busy || selected.size === 0}
            className="btn btn-primary !py-2 !px-4 text-sm flex items-center gap-2 disabled:opacity-40"
            data-testid="bulk-restore-btn"
          >
            <RotateCcw size={14} />
            {t("admin.archive.bulk_restore", "Възстанови")} ({selected.size})
          </button>
          <button
            onClick={bulkDelete}
            disabled={busy || selected.size === 0}
            className="btn btn-secondary !py-2 !px-4 text-sm flex items-center gap-2 !text-[hsl(var(--danger))] !border-[hsl(var(--danger))]/40 hover:!bg-[hsl(var(--danger))]/10 disabled:opacity-40"
            data-testid="bulk-delete-btn"
          >
            <Trash2 size={14} />
            {t("admin.archive.bulk_delete", "Изтрий завинаги")} ({selected.size})
          </button>
        </div>
      </div>

      {msg && <p className="text-sm text-[hsl(var(--accent))] mb-4">{msg}</p>}
      {err && <p className="text-sm text-[hsl(var(--danger))] mb-4 flex items-center gap-2"><AlertTriangle size={14} /> {err}</p>}

      {loading ? (
        <p className="text-sm text-[hsl(var(--ink-muted))]">…</p>
      ) : items.length === 0 ? (
        <div className="rounded-card border border-[hsl(var(--line))] p-10 text-center">
          <Archive size={28} className="mx-auto text-[hsl(var(--ink-muted))]" />
          <p className="mt-3 text-sm text-[hsl(var(--ink-muted))]">{t("admin.archive.empty", "Архивът е празен.")}</p>
        </div>
      ) : (
        <div className="rounded-card border border-[hsl(var(--line))] overflow-hidden">
          <button
            type="button"
            onClick={toggleAll}
            className="w-full px-4 py-3 flex items-center gap-3 text-sm font-medium border-b border-[hsl(var(--line))] bg-[hsl(var(--surface))] hover:bg-[hsl(var(--surface-2))] transition-colors"
            data-testid="archive-toggle-all"
          >
            {selected.size === items.length && items.length > 0 ? <CheckSquare size={16} /> : <Square size={16} />}
            {selected.size === items.length && items.length > 0
              ? t("admin.archive.deselect_all", "Премахни маркировката")
              : t("admin.archive.select_all", "Маркирай всички")}
            <span className="ml-auto text-xs text-[hsl(var(--ink-muted))]">{items.length}</span>
          </button>
          <ul>
            {items.map((a) => (
              <li
                key={a.id}
                className={`flex items-center gap-3 px-4 py-3 border-b last:border-b-0 border-[hsl(var(--line))] cursor-pointer hover:bg-[hsl(var(--surface))] transition-colors ${selected.has(a.id) ? "bg-[hsl(var(--accent-soft))]" : ""}`}
                onClick={() => toggle(a.id)}
                data-testid={`archive-row-${a.id}`}
              >
                {selected.has(a.id) ? <CheckSquare size={16} className="text-[hsl(var(--accent))] shrink-0" /> : <Square size={16} className="text-[hsl(var(--ink-muted))] shrink-0" />}
                <img
                  src={(a.images || [])[0]}
                  alt=""
                  className="w-16 h-12 rounded object-cover bg-[hsl(var(--surface))] shrink-0"
                />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">{a.title}</p>
                  <p className="text-xs text-[hsl(var(--ink-muted))] mt-0.5 font-mono truncate">
                    {a.year} · {(a.current_bid_eur || 0).toLocaleString("bg-BG")} EUR
                    {a.archived_at && ` · ${new Date(a.archived_at).toLocaleDateString()}`}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
