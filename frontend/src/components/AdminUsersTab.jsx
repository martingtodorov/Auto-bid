import React, { useEffect, useState, useCallback } from "react";
import { Search, Edit3, Shield, User as UserIcon, Check, X, Ban, RotateCcw, Trash2 } from "lucide-react";
import { api } from "../lib/apiClient";
import { formatError } from "../lib/auth";

export default function AdminUsersTab({ currentUserId }) {
  const [items, setItems] = useState([]);
  const [q, setQ] = useState("");
  const [err, setErr] = useState("");
  const [editing, setEditing] = useState(null);
  const [busyId, setBusyId] = useState(null);

  const load = useCallback(async () => {
    setErr("");
    try {
      const { data } = await api.get("/admin/users", { params: q ? { q } : {} });
      setItems(data);
    } catch (e) { setErr(formatError(e)); }
  }, [q]);

  useEffect(() => { load(); }, [load]);

  const toggleBan = async (u) => {
    const action = u.banned ? "отблокирате" : "блокирате";
    if (!window.confirm(`Сигурни ли сте, че искате да ${action} ${u.name}?`)) return;
    setErr(""); setBusyId(u.id);
    try {
      await api.post(`/admin/users/${u.id}/${u.banned ? "unban" : "ban"}`);
      await load();
    } catch (e) { setErr(formatError(e)); }
    finally { setBusyId(null); }
  };

  const deleteUser = async (u) => {
    const confirm1 = window.prompt(
      `ВНИМАНИЕ: Ще изтриете акаунта на "${u.name}" (${u.email}) БЕЗВЪЗВРАТНО.\n\n` +
      `Ще бъдат изтрити: всички наддавания, коментари, watchlist, запазени търсения и кредити.\n` +
      `Обявите им ще бъдат анонимизирани (запазени за историческа коректност).\n\n` +
      `За потвърждение напишете ИЗТРИЙ:`
    );
    if (confirm1 !== "ИЗТРИЙ") return;
    setErr(""); setBusyId(u.id);
    try {
      const { data } = await api.delete(`/admin/users/${u.id}`);
      const d = data.deleted;
      alert(`Изтрит: ${u.name}. Каскадно: ${d.bids} наддавания, ${d.comments} коментари, ${d.watches} watchers, ${d.saved_searches} търсения, ${d.auctions_anonymized} анонимизирани обяви.`);
      await load();
    } catch (e) { setErr(formatError(e)); }
    finally { setBusyId(null); }
  };

  return (
    <div className="mt-10" data-testid="admin-users-tab">
      <div className="flex flex-wrap gap-3 items-center mb-5">
        <div className="flex-1 min-w-[220px] relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[hsl(var(--ink-muted))]" />
          <input
            type="text"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && load()}
            placeholder="Търсене по име, имейл или телефон..."
            className="input pl-9"
            data-testid="admin-users-search"
          />
        </div>
        <button onClick={load} className="btn btn-primary !py-2 !px-4" data-testid="admin-users-refresh">Търси</button>
      </div>

      {err && <p className="text-sm text-[hsl(var(--danger))] mb-3">{err}</p>}

      {items.length === 0 ? (
        <div className="py-24 text-center rounded-card border border-[hsl(var(--line))]">
          <UserIcon size={28} className="mx-auto text-[hsl(var(--ink-muted))]" />
          <p className="mt-4 font-serif text-2xl">Няма потребители</p>
        </div>
      ) : (
        <div className="rounded-card border border-[hsl(var(--line))] overflow-hidden bg-white" data-testid="users-list">
          <div className="hidden md:grid grid-cols-[1.2fr_1.4fr_1fr_0.9fr_0.6fr_1.1fr] gap-3 px-5 py-3 rule-b bg-[hsl(var(--surface))] overline text-[hsl(var(--ink-muted))]">
            <span>Име</span>
            <span>Имейл</span>
            <span>Телефон</span>
            <span>Статут</span>
            <span>Роля</span>
            <span className="text-right">Действия</span>
          </div>
          {items.map((u) => (
            <div key={u.id} className={`grid grid-cols-1 md:grid-cols-[1.2fr_1.4fr_1fr_0.9fr_0.6fr_1.1fr] gap-3 items-center p-4 rule-b last:border-b-0 text-sm ${u.banned ? "bg-[hsl(var(--danger))]/5" : ""}`} data-testid={`user-row-${u.id}`}>
              <div className="font-semibold flex items-center gap-2">
                {u.name}
                {u.banned && (
                  <span className="text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded-full bg-[hsl(var(--danger))] text-white" data-testid={`banned-badge-${u.id}`}>Блокиран</span>
                )}
              </div>
              <div className="font-mono text-xs truncate">{u.email}</div>
              <div className="font-mono text-xs">{u.phone || "—"}</div>
              <div>
                {u.is_verified_dealer ? (
                  <span className="pill pill-live text-xs"><Shield size={10} /> Проверен дилър</span>
                ) : (
                  <span className="text-xs text-[hsl(var(--ink-muted))]">Частно лице</span>
                )}
              </div>
              <div>
                {u.role === "admin" ? (
                  <span className="pill text-xs bg-[hsl(var(--ink))] text-white">Админ</span>
                ) : (
                  <span className="text-xs text-[hsl(var(--ink-muted))]">Потребител</span>
                )}
              </div>
              <div className="flex flex-wrap justify-end gap-1.5">
                <button onClick={() => setEditing(u)} className="btn btn-secondary !py-1.5 !px-2.5 text-xs flex items-center gap-1" data-testid={`edit-user-${u.id}`}>
                  <Edit3 size={12} /> Редакт.
                </button>
                {u.id !== currentUserId && u.role !== "admin" && (
                  <>
                    <button
                      onClick={() => toggleBan(u)}
                      disabled={busyId === u.id}
                      className={`btn !py-1.5 !px-2.5 text-xs flex items-center gap-1 ${u.banned ? "btn-accent" : "btn-secondary !text-[hsl(var(--ink))]"}`}
                      data-testid={`${u.banned ? "unban" : "ban"}-user-${u.id}`}
                      title={u.banned ? "Отблокирай" : "Блокирай"}
                    >
                      {u.banned ? <><RotateCcw size={12} /> Отблок.</> : <><Ban size={12} /> Блокирай</>}
                    </button>
                    <button
                      onClick={() => deleteUser(u)}
                      disabled={busyId === u.id}
                      className="btn btn-secondary !py-1.5 !px-2.5 text-xs flex items-center gap-1 !text-[hsl(var(--danger))] !border-[hsl(var(--danger))]/40 hover:!bg-[hsl(var(--danger))] hover:!text-white"
                      data-testid={`delete-user-${u.id}`}
                      title="Изтрий"
                    >
                      <Trash2 size={12} /> Изтрий
                    </button>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {editing && (
        <EditUserModal
          user={editing}
          currentUserId={currentUserId}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); load(); }}
        />
      )}
    </div>
  );
}

function EditUserModal({ user, currentUserId, onClose, onSaved }) {
  const [form, setForm] = useState({
    name: user.name || "",
    email: user.email || "",
    phone: user.phone || "",
    is_verified_dealer: !!user.is_verified_dealer,
    role: user.role || "user",
  });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");
  const isSelf = user.id === currentUserId;

  const set = (k, v) => setForm((p) => ({ ...p, [k]: v }));

  const save = async () => {
    setErr(""); setSaving(true);
    try {
      const payload = { ...form };
      // Normalize phone empty string to empty (backend accepts empty to clear)
      await api.put(`/admin/users/${user.id}`, payload);
      onSaved && onSaved();
    } catch (e) { setErr(formatError(e)); }
    finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-start justify-center overflow-y-auto p-4" data-testid="edit-user-modal">
      <div className="bg-white rounded-card w-full max-w-lg my-8 shadow-xl">
        <div className="flex items-center justify-between px-6 py-4 border-b border-[hsl(var(--line))]">
          <h2 className="font-serif text-2xl">Редакция на потребител</h2>
          <button onClick={onClose} className="p-2 hover:bg-[hsl(var(--surface))] rounded-full" data-testid="edit-user-close">
            <X size={18} />
          </button>
        </div>

        <div className="p-6 space-y-4">
          {err && <div className="text-sm text-[hsl(var(--danger))]">{err}</div>}

          <div>
            <label className="overline text-[hsl(var(--ink-muted))] block mb-1.5">Имена</label>
            <input type="text" value={form.name} onChange={(e) => set("name", e.target.value)} className="input" data-testid="user-edit-name" />
          </div>
          <div>
            <label className="overline text-[hsl(var(--ink-muted))] block mb-1.5">Имейл</label>
            <input type="email" value={form.email} onChange={(e) => set("email", e.target.value)} className="input" data-testid="user-edit-email" />
          </div>
          <div>
            <label className="overline text-[hsl(var(--ink-muted))] block mb-1.5">Телефон (международен формат)</label>
            <input type="tel" value={form.phone} onChange={(e) => set("phone", e.target.value)} placeholder="+359 88 888 8888" className="input" data-testid="user-edit-phone" />
          </div>

          <div className="rounded-md border border-[hsl(var(--line))] p-4 space-y-3 bg-[hsl(var(--surface))]">
            <div className="overline text-[hsl(var(--accent))]">Статут на продавача</div>
            <label className="flex items-center gap-3 text-sm cursor-pointer">
              <input type="radio" name="dealer" checked={!form.is_verified_dealer} onChange={() => set("is_verified_dealer", false)} data-testid="user-edit-dealer-no" />
              <span><strong>Частно лице</strong> (по подразбиране)</span>
            </label>
            <label className="flex items-center gap-3 text-sm cursor-pointer">
              <input type="radio" name="dealer" checked={form.is_verified_dealer} onChange={() => set("is_verified_dealer", true)} data-testid="user-edit-dealer-yes" />
              <span><strong>Проверен дилър</strong> (показва бадж на обявите)</span>
            </label>
          </div>

          <div>
            <label className="overline text-[hsl(var(--ink-muted))] block mb-1.5">Роля</label>
            <select value={form.role} onChange={(e) => set("role", e.target.value)} disabled={isSelf} className="input" data-testid="user-edit-role">
              <option value="user">Потребител</option>
              <option value="admin">Администратор</option>
            </select>
            {isSelf && <p className="text-xs text-[hsl(var(--ink-muted))] mt-1">Не можете да променяте собствената си роля.</p>}
          </div>

          <div className="flex justify-end gap-2 pt-4 border-t border-[hsl(var(--line))]">
            <button onClick={onClose} className="btn btn-secondary" disabled={saving}>Отказ</button>
            <button onClick={save} disabled={saving} className="btn btn-primary flex items-center gap-2" data-testid="user-edit-save">
              <Check size={14} /> {saving ? "Запазване…" : "Запази"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
