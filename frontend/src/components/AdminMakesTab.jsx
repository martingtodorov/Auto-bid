import React, { useEffect, useState } from "react";
import { Tag, Plus, Trash2, Search as SearchIcon } from "lucide-react";
import { api } from "../lib/apiClient";
import { formatError, useAuth } from "../lib/auth";

export default function AdminMakesTab() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [items, setItems] = useState([]);
  const [q, setQ] = useState("");
  const [newName, setNewName] = useState("");
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  const load = async () => {
    setLoading(true); setErr("");
    try { const { data } = await api.get("/admin/makes"); setItems(data || []); }
    catch (e) { setErr(formatError(e)); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const add = async (e) => {
    e.preventDefault();
    const name = newName.trim();
    if (!name) return;
    setErr("");
    try { await api.post("/admin/makes", { name }); setNewName(""); await load(); }
    catch (e) { setErr(formatError(e)); }
  };

  const del = async (id, name) => {
    if (!window.confirm(`Изтриване на марка "${name}"? (Допустимо само ако не се използва)`)) return;
    try { await api.delete(`/admin/makes/${id}`); await load(); }
    catch (e) { setErr(formatError(e)); }
  };

  const filtered = q ? items.filter((m) => m.name.toLowerCase().includes(q.toLowerCase())) : items;

  // Group alphabetically (used for display)
  const groups = filtered.reduce((acc, m) => {
    const l = m.name[0]?.toUpperCase() || "#";
    (acc[l] = acc[l] || []).push(m);
    return acc;
  }, {});

  return (
    <div className="mt-10 max-w-[1000px]" data-testid="admin-makes-tab">
      <div className="flex items-center gap-3">
        <Tag size={18} className="text-[hsl(var(--accent))]" />
        <h2 className="font-serif text-2xl">Каталог на марки</h2>
        <span className="text-sm text-[hsl(var(--ink-muted))]">({items.length})</span>
      </div>
      <p className="mt-2 text-sm text-[hsl(var(--ink-muted))]">
        Марките, достъпни за продавачите в „Продай колата си за търг". Добавените тук автоматично се подреждат по азбучен ред.
      </p>

      {isAdmin && (
        <form onSubmit={add} className="mt-5 flex gap-3 items-stretch" data-testid="makes-add-form">
          <div className="relative flex-1">
            <Plus size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[hsl(var(--ink-muted))]" />
            <input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="Нова марка (напр. Rivian)"
              className="w-full border border-[hsl(var(--line))] h-11 pl-9 pr-3 bg-white"
              data-testid="makes-add-input"
            />
          </div>
          <button type="submit" disabled={!newName.trim()} className="btn btn-primary" data-testid="makes-add-btn">Добави</button>
        </form>
      )}

      <div className="mt-5 relative">
        <SearchIcon size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[hsl(var(--ink-muted))]" />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Търси марка…"
          className="w-full border border-[hsl(var(--line))] h-11 pl-9 pr-3 bg-white"
          data-testid="makes-search"
        />
      </div>

      {err && <p className="mt-3 text-sm text-[hsl(var(--danger))]" data-testid="makes-error">{err}</p>}

      <div className="mt-6 rounded-card border border-[hsl(var(--line))] bg-white">
        {loading ? (
          <div className="py-16 text-center text-sm text-[hsl(var(--ink-muted))]">Зареждане…</div>
        ) : filtered.length === 0 ? (
          <div className="py-16 text-center text-sm text-[hsl(var(--ink-muted))]" data-testid="makes-empty">Няма резултати.</div>
        ) : (
          <div data-testid="makes-list">
            {Object.keys(groups).sort().map((letter) => (
              <div key={letter} className="border-b last:border-b-0 border-[hsl(var(--line))]">
                <div className="px-4 py-2 bg-[hsl(var(--surface))] text-xs uppercase tracking-wider text-[hsl(var(--ink-muted))] font-medium">{letter}</div>
                <ul>
                  {groups[letter].map((m) => (
                    <li key={m.id} className="flex items-center justify-between px-4 py-2.5 hover:bg-[hsl(var(--surface))]/50" data-testid={`makes-row-${m.id}`}>
                      <span className="font-medium">{m.name}</span>
                      {isAdmin && (
                        <button onClick={() => del(m.id, m.name)} className="text-xs text-[hsl(var(--danger))] hover:underline inline-flex items-center gap-1" data-testid={`makes-delete-${m.id}`}>
                          <Trash2 size={12} /> Изтрий
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
