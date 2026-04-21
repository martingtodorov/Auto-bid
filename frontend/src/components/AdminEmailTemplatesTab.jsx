import React, { useEffect, useState } from "react";
import { Plus, Trash2, Send } from "lucide-react";
import { api } from "../lib/apiClient";
import { formatError } from "../lib/auth";

// Canned email templates — stored in site_settings.email_templates
// Keyed by admin-chosen slug (e.g., "welcome", "won_auction", "payment_reminder")
// Each template: { subject, body }

const DEFAULT_SUGGESTIONS = [
  { key: "welcome", subject: "Добре дошли в autobids.bg", body: "Здравейте {{name}},\n\nБлагодарим, че се регистрирахте в autobids.bg…" },
  { key: "payment_reminder", subject: "Напомняне за такса купувач", body: "Здравейте {{name}},\n\nЗа търга \"{{auction_title}}\" очакваме плащане на таксата…" },
  { key: "auction_approved", subject: "Вашата обява е одобрена", body: "Здравейте {{name}},\n\nВашата обява \"{{auction_title}}\" е одобрена и вече е активна." },
];

export default function AdminEmailTemplatesTab() {
  const [templates, setTemplates] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");

  // "Send test" state
  const [testKey, setTestKey] = useState("");
  const [testTo, setTestTo] = useState("");
  const [sending, setSending] = useState(false);

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const { data } = await api.get("/admin/email-templates");
        setTemplates(data || {});
      } catch (e) { setErr(formatError(e)); }
      finally { setLoading(false); }
    })();
  }, []);

  const update = (key, field, value) => {
    setTemplates((prev) => ({
      ...prev,
      [key]: { ...(prev[key] || { subject: "", body: "" }), [field]: value },
    }));
  };

  const addTemplate = (seed) => {
    const slug = seed?.key || window.prompt("Ключ на шаблона (латиница, малки букви, напр. welcome):", "");
    if (!slug || !/^[a-z0-9_\-]{2,40}$/.test(slug)) {
      if (slug !== null) alert("Невалиден ключ (позволени: латиница, цифри, _, -).");
      return;
    }
    if (templates[slug]) {
      alert("Шаблон с този ключ вече съществува.");
      return;
    }
    setTemplates((prev) => ({ ...prev, [slug]: seed ? { subject: seed.subject, body: seed.body } : { subject: "", body: "" } }));
  };

  const removeTemplate = (key) => {
    if (!window.confirm(`Изтрий шаблон „${key}"?`)) return;
    setTemplates((prev) => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
  };

  const save = async () => {
    setSaving(true); setErr(""); setMsg("");
    try {
      const { data } = await api.put("/admin/email-templates", templates);
      setTemplates(data.templates || {});
      setMsg("Запазено");
      setTimeout(() => setMsg(""), 2500);
    } catch (e) { setErr(formatError(e)); }
    finally { setSaving(false); }
  };

  const sendTest = async () => {
    if (!testKey || !testTo) { setErr("Изберете шаблон и въведете email."); return; }
    const tpl = templates[testKey];
    if (!tpl) { setErr("Шаблонът не е намерен."); return; }
    setSending(true); setErr(""); setMsg("");
    try {
      await api.post("/admin/send-email", {
        to: testTo.trim(),
        subject: tpl.subject,
        body: (tpl.body || "").replace(/\n/g, "<br />"),
      });
      setMsg(`Тестът е изпратен до ${testTo}`);
      setTimeout(() => setMsg(""), 3000);
    } catch (e) { setErr(formatError(e)); }
    finally { setSending(false); }
  };

  if (loading) return <div className="mt-10 text-[hsl(var(--ink-muted))]">Зареждане…</div>;

  const keys = Object.keys(templates);

  return (
    <div className="mt-10 space-y-6" data-testid="admin-email-templates-tab">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <div className="overline text-[hsl(var(--accent))]">Комуникация</div>
          <h2 className="font-serif text-3xl">Шаблони за имейли</h2>
          <p className="mt-2 text-sm text-[hsl(var(--ink-muted))] max-w-2xl">
            Предварително подготвени имейли, които admin/moderator може да изпраща ръчно. Поддържа променливи като <code className="text-xs font-mono">{`{{name}}`}</code>, <code className="text-xs font-mono">{`{{auction_title}}`}</code>.
          </p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <button
            onClick={() => addTemplate(null)}
            className="btn btn-secondary !py-2 !px-4 flex items-center gap-2"
            data-testid="templates-add-new"
          >
            <Plus size={14} /> Нов шаблон
          </button>
          <button
            onClick={save}
            disabled={saving}
            className="btn btn-accent !py-2 !px-5"
            data-testid="templates-save"
          >
            {saving ? "Запазване…" : "Запази всички"}
          </button>
        </div>
      </div>

      {msg && <p className="text-sm text-[hsl(var(--accent))]" data-testid="templates-msg">{msg}</p>}
      {err && <p className="text-sm text-[hsl(var(--danger))]" data-testid="templates-err">{err}</p>}

      {keys.length === 0 && (
        <div className="rounded-card border border-[hsl(var(--line))] bg-white p-6" data-testid="templates-suggestions">
          <p className="text-sm text-[hsl(var(--ink-muted))]">Още няма шаблони. Добавете бързо:</p>
          <div className="mt-3 flex gap-2 flex-wrap">
            {DEFAULT_SUGGESTIONS.map((s) => (
              <button
                key={s.key}
                onClick={() => addTemplate(s)}
                className="btn btn-secondary !py-2 !px-3 text-xs"
                data-testid={`templates-seed-${s.key}`}
              >
                + {s.key}
              </button>
            ))}
          </div>
        </div>
      )}

      {keys.map((k) => (
        <section key={k} className="rounded-card border border-[hsl(var(--line))] bg-white p-5" data-testid={`template-${k}`}>
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <div className="flex items-center gap-2">
              <span className="overline text-[hsl(var(--accent))]">Ключ</span>
              <code className="text-sm font-mono px-2 py-0.5 bg-[hsl(var(--surface))] rounded">{k}</code>
            </div>
            <button
              onClick={() => removeTemplate(k)}
              className="btn btn-secondary !py-1.5 !px-3 text-xs flex items-center gap-1.5 !border-[hsl(var(--danger))] !text-[hsl(var(--danger))]"
              data-testid={`template-remove-${k}`}
            >
              <Trash2 size={12} /> Изтрий
            </button>
          </div>
          <div className="mt-3">
            <label className="overline text-[hsl(var(--ink-muted))] block mb-1.5">Тема</label>
            <input
              type="text"
              value={templates[k]?.subject || ""}
              onChange={(e) => update(k, "subject", e.target.value)}
              maxLength={200}
              className="w-full border border-[hsl(var(--line))] h-11 px-3 text-sm"
              data-testid={`template-subject-${k}`}
            />
          </div>
          <div className="mt-3">
            <label className="overline text-[hsl(var(--ink-muted))] block mb-1.5">Съдържание (HTML или обикновен текст)</label>
            <textarea
              rows={8}
              value={templates[k]?.body || ""}
              onChange={(e) => update(k, "body", e.target.value)}
              maxLength={20000}
              className="w-full border border-[hsl(var(--line))] p-3 text-sm font-mono"
              data-testid={`template-body-${k}`}
            />
          </div>
        </section>
      ))}

      {/* Quick "send test email" */}
      {keys.length > 0 && (
        <section className="rounded-card border border-[hsl(var(--accent))]/30 bg-[hsl(var(--accent-soft))] p-5" data-testid="templates-send-test-section">
          <h3 className="font-serif text-xl">Изпрати тестов имейл</h3>
          <p className="mt-1 text-xs text-[hsl(var(--ink-muted))]">Използва текущо запазените шаблони. Запазете преди тест, ако току-що сте редактирали.</p>
          <div className="mt-3 grid grid-cols-1 md:grid-cols-[1fr_1fr_auto] gap-3">
            <select value={testKey} onChange={(e) => setTestKey(e.target.value)} className="input" data-testid="templates-test-select">
              <option value="">— избери шаблон —</option>
              {keys.map((k) => <option key={k} value={k}>{k}</option>)}
            </select>
            <input
              type="email"
              value={testTo}
              onChange={(e) => setTestTo(e.target.value)}
              placeholder="получател@email.com"
              className="input"
              data-testid="templates-test-email"
            />
            <button
              onClick={sendTest}
              disabled={sending || !testKey || !testTo}
              className="btn btn-primary !py-2 !px-5 flex items-center gap-2"
              data-testid="templates-test-send"
            >
              <Send size={14} /> {sending ? "Изпращане…" : "Изпрати"}
            </button>
          </div>
        </section>
      )}
    </div>
  );
}
