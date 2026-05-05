import React, { useEffect, useState, useRef, useCallback } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Bell, Check, CheckCheck, Gavel, Trash2, AlertTriangle } from "lucide-react";
import { useTranslation } from "react-i18next";
import { api, formatEUR } from "../lib/apiClient";
import { resolveNotification } from "../lib/notifications";
import { useAuth } from "../lib/auth";
import { auctionUrl } from "../lib/auctionUrl";

/** Bell icon + dropdown panel showing the user's recent in-app notifications.
 *  Polls /inbox/unread-count every 60s while authenticated. */
export default function NotificationBell() {
  const { user } = useAuth();
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [closing, setClosing] = useState(false);
  const [unread, setUnread] = useState(0);
  const [items, setItems] = useState([]);
  const [activeBids, setActiveBids] = useState([]);
  const [loading, setLoading] = useState(false);
  const ref = useRef(null);

  const closePanel = useCallback(() => {
    if (!open || closing) return;
    setClosing(true);
    window.setTimeout(() => {
      setOpen(false);
      setClosing(false);
    }, 160);
  }, [open, closing]);

  const togglePanel = useCallback(() => {
    if (open) closePanel();
    else setOpen(true);
  }, [open, closePanel]);

  const refreshCount = useCallback(async () => {
    if (!user) return;
    try {
      const { data } = await api.get("/inbox/unread-count");
      setUnread(Number(data?.unread || 0));
    } catch (e) {}
  }, [user]);

  const loadItems = useCallback(async () => {
    if (!user) return;
    setLoading(true);
    try {
      // Run inbox + active-bids in parallel — both feed the panel content.
      const [inboxResp, bidsResp] = await Promise.all([
        api.get("/inbox?limit=20"),
        api.get("/me/preauths").catch(() => ({ data: [] })),
      ]);
      setItems(Array.isArray(inboxResp.data?.items) ? inboxResp.data.items : []);
      setUnread(Number(inboxResp.data?.unread || 0));
      setActiveBids(Array.isArray(bidsResp.data) ? bidsResp.data : []);
    } catch (e) {}
    finally { setLoading(false); }
  }, [user]);

  useEffect(() => {
    if (!user) { setUnread(0); setItems([]); return; }
    refreshCount();
    const i = setInterval(refreshCount, 60000);
    return () => clearInterval(i);
  }, [user, refreshCount]);

  useEffect(() => {
    if (!open) return;
    loadItems();
    const onClick = (e) => {
      if (ref.current && !ref.current.contains(e.target)) closePanel();
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open, loadItems, closePanel]);

  const onItemClick = async (n) => {
    if (!n.read) {
      try { await api.post("/inbox/mark-read", { ids: [n.id] }); } catch (e) {}
    }
    closePanel();
    if (n.link) navigate(n.link);
    else if (n.auction_id) navigate(auctionUrl({ id: n.auction_id, title: n.auction_title }));
    refreshCount();
  };

  const markAllRead = async () => {
    try { await api.post("/inbox/mark-all-read"); } catch (e) {}
    setItems((items || []).map((n) => ({ ...n, read: true })));
    setUnread(0);
  };

  const clearAll = async () => {
    // Destructive — ask for confirmation. 30-day TTL cleanup happens
    // automatically for read notifications, but some users want to
    // empty their drawer manually (e.g. after resolving a backlog).
    if (!window.confirm(t("inbox.clear_all_confirm", "Изтриване на всички известия? Действието е необратимо."))) return;
    try { await api.post("/inbox/clear-all"); } catch (e) {}
    setItems([]);
    setUnread(0);
  };

  if (!user) return null;

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={togglePanel}
        className="relative w-9 h-9 rounded-full border border-[hsl(var(--line))] hover:bg-[hsl(var(--surface))] transition-colors flex items-center justify-center"
        aria-label="Notifications"
        data-testid="notification-bell"
      >
        <Bell size={18} />
        {unread > 0 && (
          <span
            className="absolute -top-1 -right-1 min-w-[18px] h-[18px] px-1 rounded-full bg-[hsl(var(--accent))] text-[10px] font-bold text-white flex items-center justify-center border-2 border-[hsl(var(--bg))]"
            data-testid="notification-unread-count"
          >
            {unread > 99 ? "99+" : unread}
          </span>
        )}
      </button>

      {open && (
        <div
          className={`absolute right-0 top-[calc(100%+8px)] w-[360px] max-w-[92vw] max-h-[480px] bg-[hsl(var(--bg))] border border-[hsl(var(--line))] rounded-lg shadow-2xl overflow-hidden flex flex-col z-50 origin-top-right ${
            closing
              ? "animate-[dropdownOut_160ms_ease-in_both]"
              : "animate-[dropdownIn_180ms_cubic-bezier(0.22,1,0.36,1)_both]"
          }`}
          data-testid="notification-panel"
        >
          <div className="flex items-center justify-between px-4 py-3 border-b border-[hsl(var(--line))]">
            <h3 className="font-serif text-base">{t("inbox.title", "Известия")}</h3>
            <div className="flex items-center gap-3">
              {unread > 0 && (
                <button
                  onClick={markAllRead}
                  className="text-xs text-[hsl(var(--accent))] hover:underline flex items-center gap-1"
                  data-testid="mark-all-read"
                >
                  <CheckCheck size={12} /> {t("inbox.mark_all_read", "Маркирай всички")}
                </button>
              )}
              {items.length > 0 && (
                <button
                  onClick={clearAll}
                  className="text-xs text-red-600 hover:underline flex items-center gap-1"
                  data-testid="clear-all-notifications"
                  title={t("inbox.clear_all_hint", "Изчиства всички известия от списъка")}
                >
                  <Trash2 size={12} /> {t("inbox.clear_all", "Изчисти")}
                </button>
              )}
            </div>
          </div>
          <div className="flex-1 overflow-y-auto">
            {/* Active bids (leading + outbid) always pinned at the very
                top. Outbid auctions are surfaced visibly so the user can
                jump back in with one click. */}
            {activeBids.length > 0 && (
              <div
                className="border-b border-[hsl(var(--line))]"
                data-testid="active-bids-section"
              >
                <div className="px-4 pt-3 pb-1 flex items-center gap-1.5 overline text-[hsl(var(--ink-muted))]">
                  <Gavel size={12} />
                  <span>{t("inbox.active_bids_title", "Активни наддавания")}</span>
                </div>
                {activeBids.map((b) => {
                  const leading = !!b.is_leading;
                  const tone = leading
                    ? "bg-emerald-50/70 hover:bg-emerald-100/80 border-l-2 border-l-emerald-500"
                    : "bg-amber-50/70 hover:bg-amber-100/80 border-l-2 border-l-amber-500";
                  return (
                    <Link
                      key={b.auction_id}
                      to={auctionUrl({ id: b.auction_id, slug: b.auction_slug, title: b.auction_title })}
                      onClick={closePanel}
                      className={`block px-4 py-3 transition-colors ${tone}`}
                      data-testid={`active-bid-row-${b.auction_id}`}
                    >
                      <div className="flex items-baseline justify-between gap-2 mb-1">
                        <span className="text-sm font-semibold text-[hsl(var(--ink))] truncate">
                          {b.auction_title}
                        </span>
                        <span
                          className={`text-[10px] uppercase tracking-wide font-bold shrink-0 px-1.5 py-0.5 rounded ${
                            leading ? "bg-emerald-600 text-white" : "bg-amber-600 text-white"
                          }`}
                          data-testid={`active-bid-status-${b.auction_id}`}
                        >
                          {leading
                            ? t("inbox.bid_leading", "Водите")
                            : t("inbox.bid_outbid", "Надминати")}
                        </span>
                      </div>
                      <div className="flex items-center justify-between gap-2 text-[11px] text-[hsl(var(--ink-muted))]">
                        <span className="flex items-center gap-1">
                          {!leading && <AlertTriangle size={10} className="text-amber-600" />}
                          {leading
                            ? t("inbox.your_bid", "Вашият бид: {{amt}}", { amt: formatEUR(b.user_max_bid_eur) })
                            : t("inbox.current_vs_yours", "Текущ {{cur}} · ваш {{my}}", {
                                cur: formatEUR(b.current_bid_eur),
                                my: formatEUR(b.user_max_bid_eur),
                              })}
                        </span>
                      </div>
                    </Link>
                  );
                })}
              </div>
            )}
            {loading && <div className="p-6 text-center text-sm text-[hsl(var(--ink-muted))]">…</div>}
            {!loading && items.length === 0 && activeBids.length === 0 && (
              <div className="p-8 text-center text-sm text-[hsl(var(--ink-muted))]" data-testid="inbox-empty">
                {t("inbox.empty", "Нямате известия")}
              </div>
            )}
            {items.map((n) => {
              const r = resolveNotification(n, t);
              return (
              <button
                key={n.id}
                onClick={() => onItemClick(n)}
                className={`w-full text-left px-4 py-3 border-b border-[hsl(var(--line))] hover:bg-[hsl(var(--surface))] transition-colors flex items-start gap-3 ${n.read ? "opacity-70" : ""}`}
                data-testid={`inbox-item-${n.id}`}
              >
                <span
                  className={`mt-1.5 w-2 h-2 rounded-full shrink-0 ${n.read ? "bg-transparent" : "bg-[hsl(var(--accent))]"}`}
                  aria-hidden="true"
                />
                <div className="flex-1 min-w-0">
                  <div className="font-semibold text-sm">{r.title}</div>
                  {r.body && <div className="text-xs text-[hsl(var(--ink-muted))] mt-0.5 line-clamp-2">{r.body}</div>}
                  <div className="text-[10px] uppercase tracking-wide text-[hsl(var(--ink-muted))] mt-1.5 font-mono">
                    {new Date(n.created_at).toLocaleString()}
                  </div>
                </div>
                {n.read && <Check size={12} className="text-[hsl(var(--ink-muted))] shrink-0 mt-1.5" />}
              </button>
              );
            })}
          </div>
          <div className="border-t border-[hsl(var(--line))] px-4 py-2.5 text-center">
            <Link
              to="/inbox"
              onClick={closePanel}
              className="text-xs text-[hsl(var(--accent))] hover:underline"
              data-testid="inbox-view-all"
            >
              {t("inbox.view_all", "Всички известия →")}
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
