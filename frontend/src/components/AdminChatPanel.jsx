import React, { useEffect, useRef, useState } from "react";
import { Send, RefreshCw, MessageCircle, Search } from "lucide-react";
import { useTranslation } from "react-i18next";
import { api } from "../lib/apiClient";

/**
 * Admin-side two-way chat. Left pane: list of user threads with last message
 * and unread badges. Right pane: selected thread's messages + reply input.
 */
export default function AdminChatPanel() {
  const { t } = useTranslation();
  const [threads, setThreads] = useState([]);
  const [active, setActive] = useState(null); // {thread_user_id, user_name, ...}
  const [messages, setMessages] = useState([]);
  const [body, setBody] = useState("");
  const [loadingThreads, setLoadingThreads] = useState(false);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [sending, setSending] = useState(false);
  const [filter, setFilter] = useState("");
  const scrollRef = useRef(null);

  const loadThreads = async () => {
    setLoadingThreads(true);
    try {
      const { data } = await api.get("/admin/chat/threads");
      setThreads(Array.isArray(data?.items) ? data.items : []);
    } catch (e) {} finally { setLoadingThreads(false); }
  };

  const loadMessages = async (uid) => {
    if (!uid) return;
    setLoadingMessages(true);
    try {
      const { data } = await api.get(`/admin/chat/threads/${uid}/messages`);
      setMessages(Array.isArray(data?.items) ? data.items : []);
      // Mark as read.
      try { await api.post(`/admin/chat/threads/${uid}/read`); } catch {}
      // Refresh threads to clear unread badge.
      loadThreads();
    } catch (e) {} finally { setLoadingMessages(false); }
  };

  useEffect(() => { loadThreads(); }, []);
  useEffect(() => { if (active) loadMessages(active.thread_user_id); }, [active?.thread_user_id]); // eslint-disable-line

  // Auto-scroll on new messages.
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages.length]);

  // Poll threads every 20s for fresh unread counts.
  useEffect(() => {
    const id = setInterval(loadThreads, 20000);
    return () => clearInterval(id);
  }, []);

  const send = async () => {
    if (!active || sending) return;
    const txt = body.trim();
    if (!txt) return;
    setSending(true);
    try {
      const { data } = await api.post(`/admin/chat/threads/${active.thread_user_id}/messages`, { body: txt });
      setMessages((arr) => [...arr, data]);
      setBody("");
      loadThreads();
    } catch (e) {} finally { setSending(false); }
  };

  const onKey = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  // Allow admin to start a new thread by typing user email/id in filter and selecting from suggestions.
  const filtered = threads.filter((t) => {
    if (!filter) return true;
    const f = filter.toLowerCase();
    return (
      (t.user_name || "").toLowerCase().includes(f) ||
      (t.user_email || "").toLowerCase().includes(f)
    );
  });

  // "Нов разговор" — pick any user to start a thread.
  const [showNew, setShowNew] = useState(false);
  const [userQuery, setUserQuery] = useState("");
  const [userSuggestions, setUserSuggestions] = useState([]);
  useEffect(() => {
    if (!showNew || !userQuery.trim()) { setUserSuggestions([]); return; }
    const ctrl = new AbortController();
    const timer = setTimeout(async () => {
      try {
        const { data } = await api.get(`/admin/users?q=${encodeURIComponent(userQuery.trim())}&limit=8`, { signal: ctrl.signal });
        setUserSuggestions(Array.isArray(data?.items) ? data.items : (Array.isArray(data) ? data : []));
      } catch {}
    }, 250);
    return () => { clearTimeout(timer); ctrl.abort(); };
  }, [userQuery, showNew]);

  const startThreadWith = (u) => {
    const stub = {
      thread_user_id: u.id,
      user_name: u.name || u.email,
      user_email: u.email,
      last_message: "",
      last_at: null,
      unread_for_admin: 0,
      total: 0,
    };
    // If thread exists, replace the stub so we don't duplicate the list.
    setThreads((arr) => arr.find((t) => t.thread_user_id === u.id) ? arr : [stub, ...arr]);
    setActive(stub);
    setShowNew(false);
    setUserQuery("");
    setUserSuggestions([]);
  };

  return (
    <div className="grid grid-cols-1 md:grid-cols-[320px_1fr] border border-[hsl(var(--line))] rounded-card overflow-hidden bg-[hsl(var(--surface))]" data-testid="admin-chat-panel" style={{ minHeight: 560 }}>
      {/* Threads list */}
      <aside className="border-r border-[hsl(var(--line))] flex flex-col">
        <div className="p-3 rule-b flex items-center gap-2">
          <Search size={14} className="text-[hsl(var(--ink-muted))]" />
          <input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder={t("chat.search_thread_placeholder")}
            className="flex-1 bg-transparent text-sm focus:outline-none"
            data-testid="admin-chat-filter"
          />
          <button onClick={loadThreads} className="p-1 rounded hover:bg-[hsl(var(--bg))]" title={t("chat.refresh")} data-testid="admin-chat-refresh">
            <RefreshCw size={12} />
          </button>
        </div>
        <div className="px-3 py-2 rule-b">
          <button
            onClick={() => setShowNew((v) => !v)}
            className="text-xs text-[hsl(var(--accent))] hover:underline"
            data-testid="admin-chat-new"
          >{t("chat.new_conversation")}</button>
          {showNew && (
            <div className="mt-2 relative">
              <input
                autoFocus
                value={userQuery}
                onChange={(e) => setUserQuery(e.target.value)}
                placeholder={t("chat.user_search_placeholder")}
                className="w-full border border-[hsl(var(--line))] bg-[hsl(var(--bg))] h-8 px-2 text-xs rounded"
                data-testid="admin-chat-user-search"
              />
              {userSuggestions.length > 0 && (
                <ul className="absolute left-0 right-0 mt-1 max-h-56 overflow-auto rounded border border-[hsl(var(--line))] bg-[hsl(var(--surface))] shadow-lg z-10">
                  {userSuggestions.map((u) => (
                    <li key={u.id}>
                      <button
                        onClick={() => startThreadWith(u)}
                        className="w-full text-left px-3 py-2 text-xs hover:bg-[hsl(var(--bg))]"
                        data-testid={`admin-chat-pick-user-${u.id}`}
                      >
                        <div className="font-semibold">{u.name || u.email}</div>
                        <div className="text-[10px] text-[hsl(var(--ink-muted))]">{u.email}</div>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
        <div className="flex-1 overflow-y-auto" data-testid="admin-chat-threads">
          {loadingThreads && <p className="p-4 text-xs text-[hsl(var(--ink-muted))]">{t("chat.loading")}</p>}
          {!loadingThreads && filtered.length === 0 && (
            <p className="p-4 text-xs text-[hsl(var(--ink-muted))] italic">{t("chat.no_threads")}</p>
          )}
          {filtered.map((thr) => {
            const isActive = active?.thread_user_id === thr.thread_user_id;
            return (
              <button
                key={thr.thread_user_id}
                onClick={() => setActive(thr)}
                className={`w-full text-left px-3 py-3 rule-b last:border-b-0 hover:bg-[hsl(var(--bg))] ${isActive ? "bg-[hsl(var(--bg))]" : ""}`}
                data-testid={`admin-chat-thread-${thr.thread_user_id}`}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="font-semibold text-sm truncate">{thr.user_name || thr.user_email}</div>
                  {thr.unread_for_admin > 0 && (
                    <span className="bg-[hsl(var(--accent))] text-white text-[10px] font-bold rounded-full min-w-[18px] h-[18px] inline-flex items-center justify-center px-1.5">
                      {thr.unread_for_admin}
                    </span>
                  )}
                </div>
                <div className="text-[10px] text-[hsl(var(--ink-muted))] truncate mt-0.5">
                  {thr.last_role === "admin" ? t("chat.you_prefix") : ""}{thr.last_message || "—"}
                </div>
                {thr.last_at && (
                  <div className="text-[10px] text-[hsl(var(--ink-muted))] mt-0.5 font-mono">
                    {new Date(thr.last_at).toLocaleString()}
                  </div>
                )}
              </button>
            );
          })}
        </div>
      </aside>

      {/* Conversation pane */}
      <section className="flex flex-col min-h-[560px]">
        {!active ? (
          <div className="flex-1 flex items-center justify-center text-sm text-[hsl(var(--ink-muted))]">
            <div className="text-center">
              <MessageCircle size={32} className="mx-auto mb-3 opacity-40" />
              {t("chat.select_or_start")}
            </div>
          </div>
        ) : (
          <>
            <div className="px-5 py-3 rule-b flex items-center justify-between" data-testid="admin-chat-active-header">
              <div>
                <div className="font-semibold text-sm">{active.user_name || active.user_email}</div>
                <div className="text-xs text-[hsl(var(--ink-muted))]">{active.user_email}</div>
              </div>
            </div>
            <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-4 space-y-3 bg-[hsl(var(--bg))]" data-testid="admin-chat-messages">
              {loadingMessages && <p className="text-xs text-[hsl(var(--ink-muted))]">{t("chat.loading")}</p>}
              {!loadingMessages && messages.length === 0 && (
                <p className="text-xs text-[hsl(var(--ink-muted))] italic">{t("chat.no_thread_messages")}</p>
              )}
              {messages.map((m) => {
                const mine = m.sender_role === "admin";
                return (
                  <div key={m.id} className={`flex ${mine ? "justify-end" : "justify-start"}`} data-testid={`admin-chat-msg-${m.id}`}>
                    <div className={`max-w-[80%] rounded-card px-3.5 py-2 text-sm whitespace-pre-wrap break-words shadow-sm ${mine ? "bg-[hsl(var(--accent))] text-white" : "bg-[hsl(var(--surface))] text-[hsl(var(--ink))] border border-[hsl(var(--line))]"}`}>
                      <div className="text-[10px] uppercase tracking-wide opacity-70 mb-0.5">
                        {mine ? `${m.sender_name || t("chat.support_default_name")} ${t("chat.admin_role_label")}` : (m.sender_name || t("chat.user_default_name"))}
                      </div>
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
                placeholder={t("chat.input_placeholder_admin")}
                className="flex-1 border border-[hsl(var(--line))] bg-[hsl(var(--bg))] rounded-card p-2.5 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-[hsl(var(--accent))]/30"
                data-testid="admin-chat-input"
              />
              <button
                type="button"
                onClick={send}
                disabled={sending || !body.trim()}
                className="btn btn-primary !px-4 !py-2.5 flex items-center gap-1.5 disabled:opacity-50"
                data-testid="admin-chat-send"
              >
                <Send size={14} /> {t("chat.send")}
              </button>
            </div>
          </>
        )}
      </section>
    </div>
  );
}
