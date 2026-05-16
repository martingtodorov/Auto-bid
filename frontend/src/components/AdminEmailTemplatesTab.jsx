import React, { useEffect, useMemo, useState } from "react";
import { Plus, Trash2, Send, RotateCcw, Eye, Lock, Globe } from "lucide-react";
import { api } from "../lib/apiClient";
import { formatError } from "../lib/auth";

// Admin-editable email templates UI.
//
// Two categories live side-by-side:
//   • SYSTEM templates — backed by the in-code registry in
//     `backend/email_templates.py`. Locked slug + locked placeholders, but
//     subject + body are fully editable. A "Reset" button restores the
//     factory default. These are the templates the system actually sends.
//   • CUSTOM templates — admin-defined slugs for manual/transactional
//     sends via the "Send test" form below or other tooling.
//
// The backend never silently bypasses overrides any more — every
// `email_*` helper renders through the same registry → DB override layer.

const LANG_BADGES = {
  bg: { label: "BG", color: "bg-emerald-100 text-emerald-700" },
  en: { label: "EN", color: "bg-sky-100 text-sky-700" },
  ro: { label: "RO", color: "bg-amber-100 text-amber-700" },
};

export default function AdminEmailTemplatesTab() {
  const [templates, setTemplates] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [preview, setPreview] = useState(null); // { slug, subject, body }
  const [tab, setTab] = useState("system");     // "system" | "custom"

  // "Send test" state
  const [testKey, setTestKey] = useState("");
  const [testTo, setTestTo] = useState("");
  const [sending, setSending] = useState(false);

  const reload = async () => {
    setLoading(true); setErr("");
    try {
      const { data } = await api.get("/admin/email-templates");
      setTemplates(data || {});
    } catch (e) { setErr(formatError(e)); }
    finally { setLoading(false); }
  };

  useEffect(() => { reload(); }, []);

  const { systemKeys, customKeys } = useMemo(() => {
    const all = Object.keys(templates);
    return {
      systemKeys: all.filter((k) => templates[k]?.system).sort(),
      customKeys: all.filter((k) => !templates[k]?.system).sort(),
    };
  }, [templates]);

  const update = (key, field, value) => {
    setTemplates((prev) => ({
      ...prev,
      [key]: { ...(prev[key] || { subject: "", body: "" }), [field]: value },
    }));
  };

  const addTemplate = () => {
    const slug = window.prompt("Ключ на нов шаблон (латиница, малки букви, напр. promo_summer):", "");
    if (!slug || !/^[a-z0-9_-]{2,40}$/.test(slug)) {
      if (slug !== null) alert("Невалиден ключ (позволени: латиница, цифри, _, -).");
      return;
    }
    if (templates[slug]) {
      alert("Шаблон с този ключ вече съществува.");
      setTab(templates[slug].system ? "system" : "custom");
      return;
    }
    setTemplates((prev) => ({
      ...prev,
      [slug]: { subject: "", body: "", header: "", system: false, lang: "bg", placeholders: [] },
    }));
    setTab("custom");
  };

  const removeTemplate = (key) => {
    const tpl = templates[key];
    if (tpl?.system) {
      alert("Системни шаблони не могат да бъдат изтривани (само reset до default).");
      return;
    }
    if (!window.confirm(`Изтрий шаблон „${key}"?`)) return;
    setTemplates((prev) => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
  };

  const resetTemplate = async (key) => {
    if (!window.confirm(`Възстанови „${key}" до фабричен default? Промените ви ще се изгубят.`)) return;
    setErr(""); setMsg("");
    try {
      await api.post(`/admin/email-templates/${encodeURIComponent(key)}/reset`);
      await reload();
      setMsg(`„${key}" е възстановен до default.`);
      setTimeout(() => setMsg(""), 2500);
    } catch (e) { setErr(formatError(e)); }
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
        subject: tpl.subject || "(no subject)",
        body: (tpl.body || "").replace(/\n/g, "<br />"),
      });
      setMsg(`Тестът е изпратен до ${testTo}`);
      setTimeout(() => setMsg(""), 3000);
    } catch (e) { setErr(formatError(e)); }
    finally { setSending(false); }
  };

  if (loading) return <div className="mt-10 text-[hsl(var(--ink-muted))]">Зареждане…</div>;

  const visibleKeys = tab === "system" ? systemKeys : customKeys;

  return (
    <div className="mt-10 space-y-6" data-testid="admin-email-templates-tab">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <div className="overline text-[hsl(var(--accent))]">Комуникация</div>
          <h2 className="font-serif text-3xl">Шаблони за имейли</h2>
          <p className="mt-2 text-sm text-[hsl(var(--ink-muted))] max-w-2xl">
            <strong>Системни</strong> шаблони се пращат автоматично от системата (потвърждение на имейл, изпреварен сте, спечелен търг и т.н.) — можете да редактирате темата и тялото им; ключът и променливите са фиксирани.{" "}
            <strong>Персонализирани</strong> шаблони се изпращат ръчно от admin/moderator.{" "}
            Поддържат се променливи като <code className="text-xs font-mono">{`{{name}}`}</code>, <code className="text-xs font-mono">{`{{auction_title}}`}</code>.
          </p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <button onClick={addTemplate} className="btn btn-secondary !py-2 !px-4 flex items-center gap-2" data-testid="templates-add-new">
            <Plus size={14} /> Нов шаблон
          </button>
          <button onClick={save} disabled={saving} className="btn btn-accent !py-2 !px-5" data-testid="templates-save">
            {saving ? "Запазване…" : "Запази всички"}
          </button>
        </div>
      </div>

      {msg && <p className="text-sm text-[hsl(var(--accent))]" data-testid="templates-msg">{msg}</p>}
      {err && <p className="text-sm text-[hsl(var(--danger))]" data-testid="templates-err">{err}</p>}

      {/* Tabs */}
      <div className="flex items-center gap-2 border-b border-[hsl(var(--line))]" data-testid="templates-tabs">
        <button
          onClick={() => setTab("system")}
          className={`px-4 py-2 -mb-px text-sm font-medium border-b-2 transition ${
            tab === "system" ? "border-[hsl(var(--accent))] text-[hsl(var(--ink))]" : "border-transparent text-[hsl(var(--ink-muted))] hover:text-[hsl(var(--ink))]"
          }`}
          data-testid="templates-tab-system"
        >
          <Lock size={12} className="inline mr-1.5" />
          Системни ({systemKeys.length})
        </button>
        <button
          onClick={() => setTab("custom")}
          className={`px-4 py-2 -mb-px text-sm font-medium border-b-2 transition ${
            tab === "custom" ? "border-[hsl(var(--accent))] text-[hsl(var(--ink))]" : "border-transparent text-[hsl(var(--ink-muted))] hover:text-[hsl(var(--ink))]"
          }`}
          data-testid="templates-tab-custom"
        >
          Персонализирани ({customKeys.length})
        </button>
      </div>

      {visibleKeys.length === 0 && tab === "custom" && (
        <div className="rounded-card border border-[hsl(var(--line))] bg-white p-6 text-sm text-[hsl(var(--ink-muted))]" data-testid="templates-empty-custom">
          Все още няма персонализирани шаблони. Натиснете <em>Нов шаблон</em> за да добавите.
        </div>
      )}

      {visibleKeys.map((k) => {
        const tpl = templates[k] || {};
        const lang = LANG_BADGES[tpl.lang] || LANG_BADGES.bg;
        const isSystem = !!tpl.system;
        return (
          <section key={k} className="rounded-card border border-[hsl(var(--line))] bg-white p-5" data-testid={`template-${k}`}>
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <div className="flex items-center gap-2 flex-wrap">
                {isSystem ? (
                  <span className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200" title="Системен шаблон — ключът и променливите са фиксирани">
                    <Lock size={10} /> СИСТЕМЕН
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-[hsl(var(--surface))] text-[hsl(var(--ink-muted))] border border-[hsl(var(--line))]">
                    ПЕРСОНАЛИЗИРАН
                  </span>
                )}
                <span className={`inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full ${lang.color}`}>
                  <Globe size={10} /> {lang.label}
                </span>
                <code className="text-sm font-mono px-2 py-0.5 bg-[hsl(var(--surface))] rounded">{k}</code>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setPreview({ slug: k, subject: tpl.subject || "", body: tpl.body || "" })}
                  className="btn btn-secondary !py-1.5 !px-3 text-xs flex items-center gap-1.5"
                  data-testid={`template-preview-${k}`}
                >
                  <Eye size={12} /> Преглед
                </button>
                {isSystem ? (
                  <button
                    onClick={() => resetTemplate(k)}
                    className="btn btn-secondary !py-1.5 !px-3 text-xs flex items-center gap-1.5"
                    data-testid={`template-reset-${k}`}
                    title="Възстанови до фабричен default"
                  >
                    <RotateCcw size={12} /> Reset
                  </button>
                ) : (
                  <button
                    onClick={() => removeTemplate(k)}
                    className="btn btn-secondary !py-1.5 !px-3 text-xs flex items-center gap-1.5 !border-[hsl(var(--danger))] !text-[hsl(var(--danger))]"
                    data-testid={`template-remove-${k}`}
                  >
                    <Trash2 size={12} /> Изтрий
                  </button>
                )}
              </div>
            </div>

            {tpl.description && (
              <p className="mt-3 text-xs text-[hsl(var(--ink-muted))] italic" data-testid={`template-desc-${k}`}>
                {tpl.description}
              </p>
            )}

            {tpl.placeholders?.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1.5" data-testid={`template-placeholders-${k}`}>
                <span className="text-[10px] text-[hsl(var(--ink-muted))] uppercase tracking-wide self-center">Променливи:</span>
                {tpl.placeholders.map((p) => (
                  <code key={p} className="text-[10px] font-mono px-1.5 py-0.5 bg-emerald-50 text-emerald-700 border border-emerald-200 rounded">
                    {`{{${p}}}`}
                  </code>
                ))}
              </div>
            )}

            <div className="mt-3">
              <label className="overline text-[hsl(var(--ink-muted))] block mb-1.5">Тема</label>
              <input
                type="text"
                value={tpl.subject || ""}
                onChange={(e) => update(k, "subject", e.target.value)}
                maxLength={200}
                className="w-full border border-[hsl(var(--line))] h-11 px-3 text-sm"
                data-testid={`template-subject-${k}`}
              />
            </div>
            {isSystem && (
              <div className="mt-3">
                <label className="overline text-[hsl(var(--ink-muted))] block mb-1.5">Заглавие в имейла (header)</label>
                <input
                  type="text"
                  value={tpl.header || ""}
                  onChange={(e) => update(k, "header", e.target.value)}
                  maxLength={200}
                  className="w-full border border-[hsl(var(--line))] h-11 px-3 text-sm"
                  data-testid={`template-header-${k}`}
                />
              </div>
            )}
            <div className="mt-3">
              <label className="overline text-[hsl(var(--ink-muted))] block mb-1.5">Съдържание (HTML)</label>
              <textarea
                rows={10}
                value={tpl.body || ""}
                onChange={(e) => update(k, "body", e.target.value)}
                maxLength={50000}
                className="w-full border border-[hsl(var(--line))] p-3 text-sm font-mono"
                data-testid={`template-body-${k}`}
              />
            </div>
          </section>
        );
      })}

      {/* Quick "send test email" */}
      {(systemKeys.length + customKeys.length) > 0 && (
        <section className="rounded-card border border-[hsl(var(--accent))]/30 bg-[hsl(var(--accent-soft))] p-5" data-testid="templates-send-test-section">
          <h3 className="font-serif text-xl">Изпрати тестов имейл</h3>
          <p className="mt-1 text-xs text-[hsl(var(--ink-muted))]">
            Използва текущо запазените шаблони. Запазете преди тест, ако току-що сте редактирали. Променливите {`{{...}}`} не се заместват в тестовия имейл — изпраща се суров HTML.
          </p>
          <div className="mt-3 grid grid-cols-1 md:grid-cols-[1fr_1fr_auto] gap-3">
            <select value={testKey} onChange={(e) => setTestKey(e.target.value)} className="input border border-[hsl(var(--line))] h-11 px-3 text-sm bg-white" data-testid="templates-test-select">
              <option value="">— избери шаблон —</option>
              <optgroup label="Системни">
                {systemKeys.map((k) => <option key={k} value={k}>{k}</option>)}
              </optgroup>
              <optgroup label="Персонализирани">
                {customKeys.map((k) => <option key={k} value={k}>{k}</option>)}
              </optgroup>
            </select>
            <input
              type="email"
              value={testTo}
              onChange={(e) => setTestTo(e.target.value)}
              placeholder="получател@email.com"
              className="border border-[hsl(var(--line))] h-11 px-3 text-sm"
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

      {/* Preview modal */}
      {preview && (
        <div
          className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4"
          onClick={() => setPreview(null)}
          data-testid="template-preview-modal"
        >
          <div
            className="bg-white rounded-card max-w-2xl w-full max-h-[85vh] overflow-hidden flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="p-4 border-b border-[hsl(var(--line))]">
              <div className="text-[10px] uppercase tracking-wider text-[hsl(var(--ink-muted))]">Преглед · {preview.slug}</div>
              <div className="font-semibold mt-0.5">{preview.subject || "(no subject)"}</div>
            </div>
            <div className="p-4 overflow-y-auto flex-1">
              <iframe
                srcDoc={preview.body}
                title="Email preview"
                className="w-full min-h-[400px] border border-[hsl(var(--line))] rounded"
                sandbox=""
              />
            </div>
            <div className="p-3 border-t border-[hsl(var(--line))] flex justify-end">
              <button onClick={() => setPreview(null)} className="btn btn-secondary !py-1.5 !px-4 text-sm" data-testid="template-preview-close">Затвори</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
