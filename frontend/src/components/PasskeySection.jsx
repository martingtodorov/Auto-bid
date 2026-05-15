import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Fingerprint, Plus, Trash2, KeyRound } from "lucide-react";
import {
  isPasskeySupported,
  registerPasskey,
  listPasskeys,
  removePasskey,
} from "../lib/passkey";

/**
 * Account-settings section for managing passkeys.
 *
 * Lists the user's enrolled credentials with device name / created /
 * last-used metadata and exposes "Add passkey" (re-auth required) and
 * "Remove" actions.
 *
 * Renders nothing if the browser doesn't support WebAuthn (e.g. older
 * Android Chrome WebView, ancient Firefox) — there's no fallback, the
 * user can keep using password + TOTP.
 */
export default function PasskeySection() {
  const { t } = useTranslation();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [deviceName, setDeviceName] = useState("");
  const [password, setPassword] = useState("");
  const [removingId, setRemovingId] = useState(null);
  const [removePwd, setRemovePwd] = useState("");
  const [err, setErr] = useState("");
  const [info, setInfo] = useState("");

  const supported = isPasskeySupported();

  const refresh = async () => {
    setLoading(true);
    try {
      setItems(await listPasskeys());
    } catch (e) {
      setErr(e?.response?.data?.detail || e?.message || "");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { if (supported) refresh(); }, [supported]);

  if (!supported) {
    return (
      <section className="border border-[hsl(var(--line))] rounded-card p-5 bg-[hsl(var(--surface))]" data-testid="passkey-section">
        <div className="flex items-center gap-2 text-sm text-[hsl(var(--ink-muted))]">
          <Fingerprint size={18} />
          {t("passkey.unsupported", "Този браузър не поддържа passkeys.")}
        </div>
      </section>
    );
  }

  const submitAdd = async (e) => {
    e.preventDefault();
    setErr(""); setInfo("");
    if (!deviceName.trim() || !password) return;
    setAdding(true);
    try {
      await registerPasskey(deviceName.trim(), password);
      setInfo(t("passkey.added_ok", "Passkey успешно добавен."));
      setDeviceName(""); setPassword(""); setShowForm(false);
      refresh();
    } catch (e) {
      setErr(e?.response?.data?.detail || e?.message || "");
    } finally {
      setAdding(false);
    }
  };

  const submitRemove = async (id) => {
    if (!removePwd) {
      setErr(t("passkey.password_required", "Въведи паролата си преди да премахнеш passkey."));
      return;
    }
    setErr(""); setInfo("");
    try {
      await removePasskey(id, removePwd);
      setInfo(t("passkey.removed_ok", "Passkey премахнат."));
      setRemovingId(null); setRemovePwd("");
      refresh();
    } catch (e) {
      setErr(e?.response?.data?.detail || e?.message || "");
    }
  };

  return (
    <section className="border border-[hsl(var(--line))] rounded-card p-5 bg-[hsl(var(--surface))]" data-testid="passkey-section">
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 rounded-full bg-[hsl(var(--accent))]/10 text-[hsl(var(--accent))] flex items-center justify-center shrink-0">
          <Fingerprint size={20} />
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="font-medium text-base">{t("passkey.title", "Passkeys (Face ID / Touch ID / Windows Hello)")}</h3>
          <p className="text-sm text-[hsl(var(--ink-muted))] mt-1">
            {t("passkey.subtitle", "По-бърз и по-сигурен начин за вход — без парола, без 6-цифрени кодове.")}
          </p>
        </div>
      </div>

      {err && <div className="mt-3 text-sm text-[hsl(var(--danger))]" data-testid="passkey-error">{err}</div>}
      {info && <div className="mt-3 text-sm text-[hsl(var(--success,#16a34a))]" data-testid="passkey-info">{info}</div>}

      {!loading && items.length > 0 && (
        <ul className="mt-4 divide-y divide-[hsl(var(--line))]" data-testid="passkey-list">
          {items.map((c) => (
            <li key={c.credential_id} className="py-3 flex items-center gap-3" data-testid={`passkey-item-${c.credential_id.slice(0, 8)}`}>
              <KeyRound size={18} className="text-[hsl(var(--ink-muted))] shrink-0" />
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium truncate">{c.device_name}</div>
                <div className="text-xs text-[hsl(var(--ink-muted))]">
                  {t("passkey.created", "Добавен")}: {new Date(c.created_at).toLocaleDateString()}
                  {c.last_used_at && (
                    <> · {t("passkey.last_used", "Последно ползван")}: {new Date(c.last_used_at).toLocaleDateString()}</>
                  )}
                </div>
              </div>
              {removingId === c.credential_id ? (
                <div className="flex items-center gap-2">
                  <input
                    type="password"
                    value={removePwd}
                    onChange={(e) => setRemovePwd(e.target.value)}
                    placeholder={t("passkey.password", "Парола")}
                    className="border border-[hsl(var(--line))] rounded px-2 py-1 text-sm w-32"
                    autoFocus
                    data-testid={`passkey-remove-pwd-${c.credential_id.slice(0, 8)}`}
                  />
                  <button
                    onClick={() => submitRemove(c.credential_id)}
                    className="text-xs text-[hsl(var(--danger))] underline"
                    data-testid={`passkey-confirm-remove-${c.credential_id.slice(0, 8)}`}
                  >
                    {t("common.delete", "Изтрий")}
                  </button>
                  <button
                    onClick={() => { setRemovingId(null); setRemovePwd(""); }}
                    className="text-xs text-[hsl(var(--ink-muted))] underline"
                  >
                    {t("common.cancel", "Откажи")}
                  </button>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => { setRemovingId(c.credential_id); setRemovePwd(""); setErr(""); setInfo(""); }}
                  className="text-xs text-[hsl(var(--ink-muted))] hover:text-[hsl(var(--danger))] flex items-center gap-1"
                  data-testid={`passkey-remove-btn-${c.credential_id.slice(0, 8)}`}
                >
                  <Trash2 size={14} /> {t("common.remove", "Премахни")}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      {!loading && items.length === 0 && (
        <p className="mt-4 text-sm text-[hsl(var(--ink-muted))]" data-testid="passkey-empty">
          {t("passkey.empty", "Все още нямаш регистрирани passkeys.")}
        </p>
      )}

      {showForm ? (
        <form onSubmit={submitAdd} className="mt-4 space-y-3" data-testid="passkey-add-form">
          <div>
            <label className="block text-xs text-[hsl(var(--ink-muted))] mb-1">
              {t("passkey.device_name", "Име на устройството")}
            </label>
            <input
              type="text"
              required
              maxLength={80}
              value={deviceName}
              onChange={(e) => setDeviceName(e.target.value)}
              placeholder={t("passkey.device_placeholder", "напр. iPhone 15, MacBook, YubiKey")}
              className="w-full border border-[hsl(var(--line))] rounded px-3 py-2 text-sm"
              data-testid="passkey-device-name"
            />
          </div>
          <div>
            <label className="block text-xs text-[hsl(var(--ink-muted))] mb-1">
              {t("passkey.confirm_password", "Потвърди паролата")}
            </label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full border border-[hsl(var(--line))] rounded px-3 py-2 text-sm"
              data-testid="passkey-password"
            />
          </div>
          <div className="flex items-center gap-2">
            <button
              type="submit"
              disabled={adding || !deviceName.trim() || !password}
              className="btn btn-primary btn-sm"
              data-testid="passkey-submit"
            >
              {adding ? t("passkey.adding", "Добавяне...") : t("passkey.create", "Създай passkey")}
            </button>
            <button
              type="button"
              onClick={() => { setShowForm(false); setErr(""); setDeviceName(""); setPassword(""); }}
              className="text-sm text-[hsl(var(--ink-muted))] underline"
            >
              {t("common.cancel", "Откажи")}
            </button>
          </div>
        </form>
      ) : (
        <button
          type="button"
          onClick={() => { setShowForm(true); setErr(""); setInfo(""); }}
          className="mt-4 inline-flex items-center gap-2 btn btn-outline btn-sm"
          data-testid="passkey-add-btn"
        >
          <Plus size={16} /> {t("passkey.add", "Добави passkey")}
        </button>
      )}
    </section>
  );
}
