import React, { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Smartphone, Monitor, Tablet, ShieldCheck, LogOut, Globe } from "lucide-react";
import { api } from "../lib/apiClient";
import { formatError } from "../lib/auth";

/**
 * Активни сесии (устройства), от които потребителят е влизал в акаунта.
 * Позволява "Изход" от конкретно устройство и "Изход от всички други устройства".
 */
export default function SessionsSection() {
  const { i18n } = useTranslation();
  const [sessions, setSessions] = useState([]);
  const [currentSid, setCurrentSid] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const load = async () => {
    setErr("");
    try {
      const { data } = await api.get("/auth/sessions");
      setSessions(data.sessions || []);
      setCurrentSid(data.current_sid || null);
    } catch (e) {
      setErr(formatError(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const revokeOne = async (sid) => {
    if (!window.confirm("Излизане от това устройство?")) return;
    setBusy(true);
    try {
      await api.delete(`/auth/sessions/${sid}`);
      await load();
    } catch (e) {
      setErr(formatError(e));
    } finally {
      setBusy(false);
    }
  };

  const revokeOthers = async () => {
    if (!window.confirm("Излизане от всички други устройства?")) return;
    setBusy(true);
    try {
      const { data } = await api.post("/auth/sessions/revoke-others");
      await load();
      window.alert(`Излязохте от ${data.revoked_count || 0} устройства.`);
    } catch (e) {
      setErr(formatError(e));
    } finally {
      setBusy(false);
    }
  };

  const fmtDate = (iso) => {
    if (!iso) return "";
    try {
      const locale = i18n.resolvedLanguage === "en" ? "en-GB" : i18n.resolvedLanguage === "ro" ? "ro-RO" : "bg-BG";
      return new Date(iso).toLocaleString(locale, {
        day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
      });
    } catch (_e) { return iso; }
  };

  const relativeTime = (iso) => {
    if (!iso) return "";
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return "току-що";
    if (mins < 60) return `преди ${mins} мин`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `преди ${hrs} ч`;
    const days = Math.floor(hrs / 24);
    if (days < 30) return `преди ${days} ${days === 1 ? "ден" : "дни"}`;
    return fmtDate(iso);
  };

  const DeviceIcon = ({ type }) => {
    if (type === "mobile") return <Smartphone size={20} />;
    if (type === "tablet") return <Tablet size={20} />;
    return <Monitor size={20} />;
  };

  const otherCount = sessions.filter((s) => !s.is_current).length;

  return (
    <section className="mt-8 rounded-card border border-[hsl(var(--line))] bg-white p-6 lg:p-8" data-testid="sessions-section">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-3">
          <ShieldCheck size={18} className="text-[hsl(var(--accent))]" />
          <h2 className="font-serif text-2xl">Активни сесии</h2>
        </div>
        {otherCount > 0 && (
          <button
            onClick={revokeOthers}
            disabled={busy}
            className="text-xs px-3 py-1.5 rounded-card border border-[hsl(var(--danger))]/40 text-[hsl(var(--danger))] hover:bg-[hsl(var(--danger))]/5 inline-flex items-center gap-1.5 disabled:opacity-50"
            data-testid="revoke-other-sessions"
          >
            <LogOut size={13} /> Изход от всички други устройства
          </button>
        )}
      </div>
      <p className="mt-3 text-sm text-[hsl(var(--ink-muted))]">
        Устройства, които в момента имат достъп до акаунта Ви. Ако виждате непознато устройство, прекратете сесията и сменете паролата си.
      </p>

      {loading ? (
        <div className="mt-6 py-10 text-center text-sm text-[hsl(var(--ink-muted))]">Зареждане…</div>
      ) : err ? (
        <div className="mt-6 py-6 text-sm text-[hsl(var(--danger))]" data-testid="sessions-error">{err}</div>
      ) : sessions.length === 0 ? (
        <div className="mt-6 py-10 text-center text-sm text-[hsl(var(--ink-muted))] rounded-card bg-[hsl(var(--surface))] border border-dashed border-[hsl(var(--line))]">
          Няма активни сесии.
        </div>
      ) : (
        <div className="mt-6 space-y-3" data-testid="sessions-list">
          {sessions.map((s) => (
            <div
              key={s.id}
              className={`flex items-start gap-4 p-4 rounded-card border ${s.is_current ? "border-[hsl(var(--accent))]/40 bg-[hsl(var(--accent))]/5" : "border-[hsl(var(--line))]"}`}
              data-testid={`session-${s.id}`}
            >
              <div className={`mt-1 ${s.is_current ? "text-[hsl(var(--accent))]" : "text-[hsl(var(--ink-muted))]"}`}>
                <DeviceIcon type={s.device_type} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-semibold text-sm" data-testid={`session-device-${s.id}`}>{s.device_label}</span>
                  {s.is_current && (
                    <span className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded-full bg-[hsl(var(--accent))] text-white" data-testid={`session-current-${s.id}`}>
                      Текуща сесия
                    </span>
                  )}
                  {s.remember && (
                    <span className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded-full bg-[hsl(var(--surface-2,var(--surface)))] text-[hsl(var(--ink-muted))] border border-[hsl(var(--line))]">
                      Запомни ме
                    </span>
                  )}
                </div>
                <div className="mt-1 text-xs text-[hsl(var(--ink-muted))]">
                  {s.browser} · {s.os}
                </div>
                <div className="mt-1 text-xs text-[hsl(var(--ink-muted))] flex items-center gap-3 flex-wrap">
                  {s.ip && (
                    <span className="inline-flex items-center gap-1">
                      <Globe size={11} /> {s.ip}
                    </span>
                  )}
                  <span>Последна активност: {relativeTime(s.last_seen_at)}</span>
                </div>
              </div>
              {!s.is_current && (
                <button
                  onClick={() => revokeOne(s.id)}
                  disabled={busy}
                  className="text-xs px-3 py-1.5 rounded-card border border-[hsl(var(--line))] hover:border-[hsl(var(--danger))]/40 hover:text-[hsl(var(--danger))] inline-flex items-center gap-1.5 disabled:opacity-50 whitespace-nowrap"
                  data-testid={`revoke-session-${s.id}`}
                >
                  <LogOut size={12} /> Изход
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
