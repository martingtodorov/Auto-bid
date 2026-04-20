import React, { useEffect, useState } from "react";
import { X, Shield, ShieldOff, BadgeCheck, Ban, UserCog, Mail, MessageSquare, Trash2, FileText } from "lucide-react";
import { api } from "../lib/apiClient";
import { formatError } from "../lib/auth";

/**
 * Admin moderation panel for a single user.
 * Shows: basic info, suspend/unsuspend, verify/unverify seller, resend verification,
 *        internal notes (add/remove), VIN request history.
 */
export default function AdminUserDetailModal({ userId, onClose, onChanged }) {
  const [u, setU] = useState(null);
  const [notes, setNotes] = useState([]);
  const [vin, setVin] = useState([]);
  const [newNote, setNewNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");

  const load = async () => {
    setErr("");
    try {
      const [userRes, notesRes, vinRes] = await Promise.all([
        api.get(`/admin/users/${userId}`),
        api.get(`/admin/users/${userId}/notes`),
        api.get(`/admin/users/${userId}/vin-requests`),
      ]);
      setU(userRes.data);
      setNotes(notesRes.data || []);
      setVin(vinRes.data || []);
    } catch (e) { setErr(formatError(e)); }
  };

  useEffect(() => { if (userId) load(); /* eslint-disable-next-line */ }, [userId]);

  const action = async (url, method = "POST", body = null) => {
    setBusy(true); setErr(""); setMsg("");
    try {
      if (method === "POST") await api.post(url, body);
      else if (method === "DELETE") await api.delete(url);
      await load();
      onChanged?.();
      setMsg("Готово");
      setTimeout(() => setMsg(""), 2000);
    } catch (e) { setErr(formatError(e)); }
    finally { setBusy(false); }
  };

  const addNote = async () => {
    const text = newNote.trim();
    if (!text) return;
    setBusy(true); setErr("");
    try {
      await api.post(`/admin/users/${userId}/notes`, { text });
      setNewNote("");
      await load();
    } catch (e) { setErr(formatError(e)); }
    finally { setBusy(false); }
  };

  if (!userId) return null;
  if (!u) {
    return (
      <Overlay onClose={onClose}>
        <div className="py-16 text-center text-sm text-[hsl(var(--ink-muted))]">Зареждане…</div>
      </Overlay>
    );
  }

  return (
    <Overlay onClose={onClose}>
      <div className="p-6 border-b border-[hsl(var(--line))] flex items-start justify-between gap-4" data-testid="admin-user-modal">
        <div className="min-w-0">
          <div className="overline text-[hsl(var(--accent))]">Модерация на потребител</div>
          <h2 className="font-serif text-2xl mt-1 truncate">{u.name}</h2>
          <div className="mt-1 text-sm text-[hsl(var(--ink-muted))] font-mono truncate">{u.email}</div>
          <div className="mt-3 flex flex-wrap gap-2 text-xs">
            <Chip>Роля: {u.role}</Chip>
            {u.is_verified_dealer && <Chip color="accent">Верифициран</Chip>}
            {u.suspended && <Chip color="danger">Спрян</Chip>}
            {u.banned && <Chip color="danger">Блокиран</Chip>}
            {u.totp_enabled && <Chip>2FA</Chip>}
          </div>
        </div>
        <button onClick={onClose} className="p-1 hover:bg-[hsl(var(--surface))] rounded-card" aria-label="close"><X size={18} /></button>
      </div>

      <div className="p-6 space-y-6">
        {err && <div className="text-sm text-[hsl(var(--danger))]" data-testid="modal-error">{err}</div>}
        {msg && <div className="text-sm text-[hsl(var(--accent))]">{msg}</div>}

        {/* Actions */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2" data-testid="user-actions">
          {u.suspended ? (
            <ActBtn icon={Shield} onClick={() => action(`/admin/users/${userId}/unsuspend`)} disabled={busy} testid="act-unsuspend">Възстанови</ActBtn>
          ) : (
            <ActBtn icon={ShieldOff} onClick={() => action(`/admin/users/${userId}/suspend`)} disabled={busy || u.role !== "user"} danger testid="act-suspend">Спри бидване</ActBtn>
          )}
          {u.is_verified_dealer ? (
            <ActBtn icon={BadgeCheck} onClick={() => action(`/admin/users/${userId}/unverify-seller`)} disabled={busy} testid="act-unverify">Премахни верификация</ActBtn>
          ) : (
            <ActBtn icon={BadgeCheck} onClick={() => action(`/admin/users/${userId}/verify-seller`)} disabled={busy} testid="act-verify">Верифицирай</ActBtn>
          )}
          <ActBtn icon={Mail} onClick={() => action(`/admin/users/${userId}/resend-verification`)} disabled={busy} testid="act-resend">Прати email</ActBtn>
          {u.banned ? (
            <ActBtn icon={Ban} onClick={() => action(`/admin/users/${userId}/unban`)} disabled={busy} testid="act-unban">Разблокирай</ActBtn>
          ) : (
            <ActBtn icon={Ban} onClick={() => action(`/admin/users/${userId}/ban`)} disabled={busy || u.role !== "user"} danger testid="act-ban">Пълен ban</ActBtn>
          )}
        </div>

        {/* Notes */}
        <div>
          <div className="flex items-center gap-2 overline text-[hsl(var(--accent))] mb-3">
            <FileText size={14} /> Вътрешни бележки ({notes.length})
          </div>
          <div className="flex gap-2">
            <input value={newNote} onChange={(e) => setNewNote(e.target.value)} placeholder="Добави бележка (не се вижда от потребителя)…" className="flex-1 border border-[hsl(var(--line))] h-11 px-3 text-sm" data-testid="note-input" />
            <button onClick={addNote} disabled={!newNote.trim() || busy} className="btn btn-primary !px-4" data-testid="note-add-btn">Добави</button>
          </div>
          {notes.length > 0 && (
            <ul className="mt-3 space-y-2" data-testid="notes-list">
              {notes.map((n) => (
                <li key={n.id} className="rounded-card bg-[hsl(var(--surface))] p-3 border border-[hsl(var(--line))] text-sm" data-testid={`note-${n.id}`}>
                  <div className="flex justify-between items-start gap-3">
                    <p className="whitespace-pre-line">{n.text}</p>
                    <button onClick={() => action(`/admin/users/${userId}/notes/${n.id}`, "DELETE")} className="text-[hsl(var(--ink-muted))] hover:text-[hsl(var(--danger))] shrink-0" title="Изтрий"><Trash2 size={14} /></button>
                  </div>
                  <div className="mt-1 text-xs text-[hsl(var(--ink-muted))]">{n.author_name} ({n.author_role}) · {new Date(n.at).toLocaleString("bg-BG")}</div>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* VIN history */}
        <div>
          <div className="flex items-center gap-2 overline text-[hsl(var(--accent))] mb-3">
            <MessageSquare size={14} /> VIN заявки ({vin.length})
          </div>
          {vin.length === 0 ? (
            <p className="text-sm text-[hsl(var(--ink-muted))]">Няма заявки за VIN.</p>
          ) : (
            <ul className="space-y-1 text-sm" data-testid="vin-list">
              {vin.map((v, i) => (
                <li key={v.id || i} className="text-xs font-mono text-[hsl(var(--ink-muted))]">
                  {new Date(v.created_at).toLocaleString("bg-BG")} → обява {v.auction_id?.slice(0, 8)}…
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </Overlay>
  );
}

function Overlay({ onClose, children }) {
  return (
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-start justify-center p-4 overflow-auto" onClick={onClose}>
      <div className="bg-white rounded-card max-w-2xl w-full my-8" onClick={(e) => e.stopPropagation()}>{children}</div>
    </div>
  );
}

function Chip({ children, color }) {
  const cls = color === "accent" ? "bg-[hsl(var(--accent))] text-white" : color === "danger" ? "bg-[hsl(var(--danger))] text-white" : "bg-[hsl(var(--surface))] text-[hsl(var(--ink))]";
  return <span className={`px-2 py-0.5 rounded-full ${cls}`}>{children}</span>;
}

function ActBtn({ icon: Icon, onClick, disabled, children, testid, danger }) {
  return (
    <button onClick={onClick} disabled={disabled} className={`flex items-center justify-center gap-1.5 text-xs px-3 py-2 rounded-card border disabled:opacity-40 ${danger ? "border-[hsl(var(--danger))] text-[hsl(var(--danger))] hover:bg-[hsl(var(--danger))] hover:text-white" : "border-[hsl(var(--line))] hover:bg-[hsl(var(--surface))]"}`} data-testid={testid}>
      <Icon size={13} /> {children}
    </button>
  );
}
