import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { CheckCheck } from "lucide-react";
import { api } from "../lib/apiClient";
import { resolveNotification } from "../lib/notifications";
import UserChatPanel from "../components/UserChatPanel";

/** Full-page inbox listing the user's notifications with pagination. */
export default function InboxPage() {
  const { t } = useTranslation();
  const [items, setItems] = useState([]);
  const [unread, setUnread] = useState(0);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/inbox?limit=200");
      setItems(Array.isArray(data?.items) ? data.items : []);
      setUnread(Number(data?.unread || 0));
    } catch (e) {} finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  const markAll = async () => {
    try { await api.post("/inbox/mark-all-read"); } catch (e) {}
    setItems((arr) => arr.map((n) => ({ ...n, read: true })));
    setUnread(0);
  };

  const markOne = async (id) => {
    try { await api.post("/inbox/mark-read", { ids: [id] }); } catch (e) {}
    setItems((arr) => arr.map((n) => (n.id === id ? { ...n, read: true } : n)));
    setUnread((c) => Math.max(0, c - 1));
  };

  return (
    <main className="min-h-[calc(100vh-160px)] max-w-[920px] mx-auto px-4 sm:px-6 lg:px-10 py-12">
      <div className="flex items-center justify-between mb-8 flex-wrap gap-3">
        <div>
          <p className="overline text-[hsl(var(--accent))]">{t("inbox.overline", "Inbox")}</p>
          <h1 className="hero-headline text-4xl mt-2">{t("inbox.title", "Известия")}</h1>
          {unread > 0 && (
            <p className="text-sm text-[hsl(var(--ink-muted))] mt-1" data-testid="inbox-unread-count">
              {t("inbox.unread_count", "{{count}} непрочетени", { count: unread })}
            </p>
          )}
        </div>
        {unread > 0 && (
          <button
            onClick={markAll}
            className="btn btn-secondary !py-2 flex items-center gap-2"
            data-testid="inbox-mark-all"
          >
            <CheckCheck size={14} /> {t("inbox.mark_all_read", "Маркирай всички")}
          </button>
        )}
      </div>

      <UserChatPanel />

      {loading && <p className="text-sm text-[hsl(var(--ink-muted))]">…</p>}
      {!loading && items.length === 0 && (
        <div className="rounded-card border border-[hsl(var(--line))] p-12 text-center" data-testid="inbox-empty-page">
          <p className="text-sm text-[hsl(var(--ink-muted))]">{t("inbox.empty", "Нямате известия")}</p>
        </div>
      )}

      <ul className="rounded-card border border-[hsl(var(--line))] overflow-hidden">
        {items.map((n) => {
          const r = resolveNotification(n, t);
          const dest = n.link || (n.auction_id ? `/auctions/${n.auction_id}` : null);
          const inner = (
            <>
              <span
                className={`mt-2 w-2.5 h-2.5 rounded-full shrink-0 ${n.read ? "bg-transparent" : "bg-[hsl(var(--accent))]"}`}
              />
              <div className="flex-1 min-w-0">
                <div className="font-semibold">{r.title}</div>
                {r.body && <div className="text-sm text-[hsl(var(--ink-muted))] mt-0.5">{r.body}</div>}
                <div className="text-xs text-[hsl(var(--ink-muted))] mt-1.5 font-mono">
                  {new Date(n.created_at).toLocaleString()}
                </div>
              </div>
            </>
          );
          return (
            <li key={n.id} className={`border-b last:border-b-0 border-[hsl(var(--line))] ${n.read ? "opacity-70" : ""}`} data-testid={`inbox-row-${n.id}`}>
              {dest ? (
                <Link
                  to={dest}
                  onClick={() => !n.read && markOne(n.id)}
                  className="px-5 py-4 flex items-start gap-3 hover:bg-[hsl(var(--surface))]"
                >
                  {inner}
                </Link>
              ) : (
                <div className="px-5 py-4 flex items-start gap-3">{inner}</div>
              )}
            </li>
          );
        })}
      </ul>
    </main>
  );
}
