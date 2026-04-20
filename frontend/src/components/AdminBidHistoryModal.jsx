import React, { useEffect, useState } from "react";
import { X, Gavel, AlertOctagon, Ban, Check, Zap } from "lucide-react";
import { api, formatEUR } from "../lib/apiClient";
import { formatError } from "../lib/auth";

/**
 * Admin modal: full bid history for an auction.
 * Features: invalidate a bid (with reason), block bidder from this auction, anti-sniping flag visible.
 */
export default function AdminBidHistoryModal({ auctionId, auctionTitle, onClose }) {
  const [bids, setBids] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(null);

  const load = async () => {
    setLoading(true); setErr("");
    try {
      const { data } = await api.get(`/admin/auctions/${auctionId}/bids`);
      setBids(data || []);
    } catch (e) { setErr(formatError(e)); }
    finally { setLoading(false); }
  };

  useEffect(() => { if (auctionId) load(); /* eslint-disable-next-line */ }, [auctionId]);

  const invalidate = async (b) => {
    const reason = window.prompt(`Защо инвалидирате този бид от ${b.user_name} (${formatEUR(b.amount_eur)})?\n(мин. 3 символа)`);
    if (!reason || reason.trim().length < 3) return;
    setBusy(b.id);
    try {
      await api.post(`/admin/bids/${b.id}/invalidate`, { reason: reason.trim() });
      await load();
    } catch (e) { setErr(formatError(e)); }
    finally { setBusy(null); }
  };

  const block = async (b) => {
    const reason = window.prompt(`Блокиране на ${b.user_name} за тази обява?\n(Незадължителна причина)`);
    if (reason === null) return;
    setBusy(b.id);
    try {
      await api.post(`/admin/auctions/${auctionId}/block-bidder`, { user_id: b.user_id, reason: reason.trim() });
      await load();
    } catch (e) { setErr(formatError(e)); }
    finally { setBusy(null); }
  };

  const unblock = async (b) => {
    setBusy(b.id);
    try {
      await api.delete(`/admin/auctions/${auctionId}/block-bidder/${b.user_id}`);
      await load();
    } catch (e) { setErr(formatError(e)); }
    finally { setBusy(null); }
  };

  if (!auctionId) return null;

  return (
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-start justify-center p-4 overflow-auto" onClick={onClose}>
      <div className="bg-white rounded-card max-w-4xl w-full my-8" onClick={(e) => e.stopPropagation()} data-testid="admin-bids-modal">
        <div className="p-5 border-b border-[hsl(var(--line))] flex items-start justify-between">
          <div>
            <div className="flex items-center gap-2 overline text-[hsl(var(--accent))]"><Gavel size={14} /> Пълна история на бидовете</div>
            <h2 className="font-serif text-xl mt-1">{auctionTitle}</h2>
          </div>
          <button onClick={onClose} className="p-1 hover:bg-[hsl(var(--surface))] rounded-card"><X size={18} /></button>
        </div>
        <div className="p-5">
          {err && <div className="text-sm text-[hsl(var(--danger))] mb-3" data-testid="bids-error">{err}</div>}
          {loading ? (
            <div className="py-10 text-center text-sm text-[hsl(var(--ink-muted))]">Зареждане…</div>
          ) : bids.length === 0 ? (
            <div className="py-10 text-center text-sm text-[hsl(var(--ink-muted))]" data-testid="bids-empty">Няма бидове.</div>
          ) : (
            <div className="rounded-card border border-[hsl(var(--line))] overflow-hidden" data-testid="bids-list">
              <table className="w-full text-sm">
                <thead className="bg-[hsl(var(--surface))] text-xs uppercase text-[hsl(var(--ink-muted))]">
                  <tr>
                    <th className="text-left p-3">Време</th>
                    <th className="text-left p-3">Бидър</th>
                    <th className="text-right p-3">Сума</th>
                    <th className="text-center p-3">Флагове</th>
                    <th className="text-right p-3">Действия</th>
                  </tr>
                </thead>
                <tbody>
                  {bids.map((b) => (
                    <tr key={b.id} className={`border-t border-[hsl(var(--line))] ${b.invalidated ? "opacity-50 line-through" : ""}`} data-testid={`bid-row-${b.id}`}>
                      <td className="p-3 text-xs font-mono text-[hsl(var(--ink-muted))] whitespace-nowrap">{new Date(b.created_at).toLocaleString("bg-BG")}</td>
                      <td className="p-3">
                        <div className="font-medium">{b.user_name}</div>
                        <div className="text-xs font-mono text-[hsl(var(--ink-muted))]">{b.user_id?.slice(0, 8)}…</div>
                      </td>
                      <td className="p-3 text-right font-serif text-base">{formatEUR(b.amount_eur)}</td>
                      <td className="p-3 text-center">
                        <div className="flex justify-center gap-1.5 flex-wrap">
                          {b.triggered_extension && <span className="inline-flex items-center gap-1 text-xs px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-800" title="Задействал anti-sniping"><Zap size={10} /> anti-snipe</span>}
                          {b.invalidated && <span className="inline-flex items-center gap-1 text-xs px-1.5 py-0.5 rounded-full bg-[hsl(var(--danger))] text-white" title={b.invalidated_reason}><AlertOctagon size={10} /> инвалидиран</span>}
                          {b.is_blocked_on_auction && <span className="inline-flex items-center gap-1 text-xs px-1.5 py-0.5 rounded-full bg-[hsl(var(--ink))] text-white"><Ban size={10} /> блокиран</span>}
                        </div>
                      </td>
                      <td className="p-3 text-right">
                        <div className="flex justify-end gap-1">
                          {!b.invalidated && (
                            <button onClick={() => invalidate(b)} disabled={busy === b.id} className="text-xs px-2 py-1 border border-[hsl(var(--line))] rounded-card hover:bg-[hsl(var(--danger))] hover:text-white hover:border-[hsl(var(--danger))]" data-testid={`invalidate-${b.id}`} title="Инвалидирай">
                              <AlertOctagon size={12} />
                            </button>
                          )}
                          {b.is_blocked_on_auction ? (
                            <button onClick={() => unblock(b)} disabled={busy === b.id} className="text-xs px-2 py-1 border border-[hsl(var(--accent))] text-[hsl(var(--accent))] rounded-card" data-testid={`unblock-${b.id}`} title="Отблокирай за търга">
                              <Check size={12} />
                            </button>
                          ) : (
                            <button onClick={() => block(b)} disabled={busy === b.id} className="text-xs px-2 py-1 border border-[hsl(var(--line))] rounded-card hover:bg-[hsl(var(--ink))] hover:text-white" data-testid={`block-${b.id}`} title="Блокирай за този търг">
                              <Ban size={12} />
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
