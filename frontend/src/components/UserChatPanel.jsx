import React, { useEffect, useRef, useState } from "react";
import { Send, MessageCircle, RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";
import { api } from "../lib/apiClient";

/**
 * Two-way chat between an end user and admin/moderator support.
 * One thread per user — every admin sees the same conversation.
 *
 * Used by the customer in their Inbox (current user is the thread owner).
 */
export default function UserChatPanel() {
  const { t } = useTranslation();
  const [items, setItems] = useState([]);
  const [body, setBody] = useState("");
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [open, setOpen] = useState(true);
  const scrollRef = useRef(null);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/me/chat/messages");
      setItems(Array.isArray(data?.items) ? data.items : []);
      // Mark admin messages read once user opens the chat.
      if ((data?.unread || 0) > 0) {
        try { await api.post("/me/chat/read"); } catch {}
      }
    } catch (e) {
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  // Auto-scroll to the bottom whenever items change.
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [items.length, open]);

  const send = async () => {
    const txt = body.trim();
    if (!txt || sending) return;
    setSending(true);
    try {
      const { data } = await api.post("/me/chat/messages", { body: txt });
      setItems((arr) => [...arr, data]);
      setBody("");
    } catch (e) {
    } finally { setSending(false); }
  };

  const onKey = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  return (
    <section
      className="rounded-card border border-[hsl(var(--line))] bg-[hsl(var(--surface))] overflow-hidden mb-8"
      data-testid="user-chat-panel"
    >
      <header
        className="px-5 py-3 rule-b flex items-center justify-between gap-3 cursor-pointer select-none"
        onClick={() => setOpen((v) => !v)}
        data-testid="user-chat-toggle"
      >
        <div className="flex items-center gap-2">
          <MessageCircle size={16} className="text-[hsl(var(--accent))]" />
          <span className="font-semibold text-sm">{t("chat.support_title")}</span>
          <span className="text-xs text-[hsl(var(--ink-muted))]">· {t("chat.support_subtitle")}</span>
        </div>
        <div className="flex items-center gap-2 text-xs text-[hsl(var(--ink-muted))]">
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); load(); }}
            className="p-1 rounded hover:bg-[hsl(var(--bg))]"
            title={t("chat.refresh")}
            data-testid="user-chat-refresh"
          >
            <RefreshCw size={12} />
          </button>
          <span>{open ? "—" : "+"}</span>
        </div>
      </header>

      {open && (
        <>
          <div
            ref={scrollRef}
            className="h-72 overflow-y-auto px-4 py-4 space-y-3 bg-[hsl(var(--bg))]"
            data-testid="user-chat-scroll"
          >
            {loading && <p className="text-xs text-[hsl(var(--ink-muted))]">{t("chat.loading")}</p>}
            {!loading && items.length === 0 && (
              <p className="text-xs text-[hsl(var(--ink-muted))] italic">
                {t("chat.no_messages")}
              </p>
            )}
            {items.map((m) => {
              const mine = m.sender_role === "user";
              return (
                <div
                  key={m.id}
                  className={`flex ${mine ? "justify-end" : "justify-start"}`}
                  data-testid={`user-chat-msg-${m.id}`}
                >
                  <div
                    className={`max-w-[80%] rounded-card px-3.5 py-2 text-sm whitespace-pre-wrap break-words shadow-sm ${
                      mine
                        ? "bg-[hsl(var(--accent))] text-white"
                        : "bg-[hsl(var(--surface))] text-[hsl(var(--ink))] border border-[hsl(var(--line))]"
                    }`}
                  >
                    {!mine && (
                      <div className="text-[10px] uppercase tracking-wide opacity-70 mb-0.5">
                        {m.sender_name || t("chat.support_default_name")}
                      </div>
                    )}
                    <div>{m.body}</div>
                    <div className={`text-[10px] mt-1 ${mine ? "text-white/70" : "text-[hsl(var(--ink-muted))]"} text-right`}>
                      {new Date(m.created_at).toLocaleString()}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          <div className="p-3 rule-t flex items-end gap-2 bg-[hsl(var(--surface))]">
            <textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              onKeyDown={onKey}
              rows={2}
              placeholder={t("chat.input_placeholder")}
              className="flex-1 border border-[hsl(var(--line))] bg-[hsl(var(--bg))] rounded-card p-2.5 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-[hsl(var(--accent))]/30"
              data-testid="user-chat-input"
            />
            <button
              type="button"
              onClick={send}
              disabled={sending || !body.trim()}
              className="btn btn-primary !px-4 !py-2.5 flex items-center gap-1.5 disabled:opacity-50"
              data-testid="user-chat-send"
            >
              <Send size={14} /> {t("chat.send")}
            </button>
          </div>
        </>
      )}
    </section>
  );
}
