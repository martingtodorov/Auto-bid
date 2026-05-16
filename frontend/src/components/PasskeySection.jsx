import { useEffect, useState, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { Fingerprint, Plus, Trash2, KeyRound, Pencil, Check, X, Lock } from "lucide-react";
import {
  isPasskeySupported,
  registerPasskey,
  listPasskeys,
  removePasskey,
  renamePasskey,
  getReauthStatus,
  verifyReauth,
} from "../lib/passkey";

/**
 * Account-settings section for managing passkeys.
 *
 * Auth model:
 *   • The page first asks the backend whether the current session is
 *     "recently authenticated" (password verified in the last 10 min).
 *   • If yes — Add / Remove / Rename are available with a single click.
 *   • If no — a one-time inline password gate appears at the top. After
 *     verification the rest of the controls become live without a page
 *     reload. The gate is automatically re-shown if the user takes
 *     longer than the freshness window.
 *
 * Device name is auto-derived from User-Agent on the backend; users can
 * rename inline later.
 */
export default function PasskeySection() {
  const { t } = useTranslation();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);
  const [removingId, setRemovingId] = useState(null);
  const [renamingId, setRenamingId] = useState(null);
  const [renameValue, setRenameValue] = useState("");
  const [reauthRecent, setReauthRecent] = useState(false);
  const [reauthPwd, setReauthPwd] = useState("");
  const [reauthBusy, setReauthBusy] = useState(false);
  const [err, setErr] = useState("");
  const [info, setInfo] = useState("");

  const supported = isPasskeySupported();

  const refreshStatus = useCallback(async () => {
    try {
      const s = await getReauthStatus();
      setReauthRecent(!!s.recent);
    } catch {
      setReauthRecent(false);
    }
  }, []);

  const refreshList = useCallback(async () => {
    setLoading(true);
    try {
      setItems(await listPasskeys());
    } catch (e) {
      setErr(e?.response?.data?.detail || e?.message || "");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!supported) return;
    refreshStatus();
    refreshList();
  }, [supported, refreshStatus, refreshList]);

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

  // Map any 401 from add/remove/rename back to "must re-auth" state.
  const handleAuthError = (e) => {
    const status = e?.response?.status;
    const needs = status === 401 || e?.response?.headers?.["x-reauth-required"];
    if (needs) {
      setReauthRecent(false);
      setErr(t("passkey.session_expired", "Сесията изтече. Въведи паролата отново."));
    } else {
      setErr(e?.response?.data?.detail || e?.message || "");
    }
  };

  const submitReauth = async (e) => {
    e?.preventDefault?.();
    if (!reauthPwd) return;
    setErr(""); setInfo(""); setReauthBusy(true);
    try {
      await verifyReauth(reauthPwd);
      setReauthRecent(true);
      setReauthPwd("");
      setInfo(t("passkey.reauth_ok", "Потвърдено. Промените са активни за 10 минути."));
    } catch (e) {
      setErr(e?.response?.data?.detail || e?.message || "");
    } finally {
      setReauthBusy(false);
    }
  };

  const addPasskey = async () => {
    setErr(""); setInfo(""); setAdding(true);
    try {
      const { device_name } = await registerPasskey();
      setInfo(t("passkey.added_ok_named", { device: device_name, defaultValue: `Passkey "${device_name}" добавен.` }));
      refreshList();
    } catch (e) {
      handleAuthError(e);
    } finally {
      setAdding(false);
    }
  };

  const confirmRemove = async (id) => {
    setErr(""); setInfo("");
    try {
      await removePasskey(id);
      setInfo(t("passkey.removed_ok", "Passkey премахнат."));
      setRemovingId(null);
      refreshList();
    } catch (e) {
      handleAuthError(e);
    }
  };

  const startRename = (item) => {
    setRenamingId(item.credential_id);
    setRenameValue(item.device_name || "");
    setErr(""); setInfo("");
  };

  const submitRename = async (id) => {
    const name = (renameValue || "").trim();
    if (!name) return;
    setErr(""); setInfo("");
    try {
      await renamePasskey(id, name);
      setRenamingId(null);
      setRenameValue("");
      refreshList();
    } catch (e) {
      handleAuthError(e);
    }
  };

  // NOTE: Re-auth gate is intentionally inlined in the JSX below.
  // Defining it as a nested component (e.g. `const ReauthGate = () => …`)
  // here would make React see a NEW component identity on every parent
  // render — which happens on every keystroke because `reauthPwd` is in
  // state — causing the password <input> to unmount + remount and lose
  // focus after the first character. Keep this JSX inline. See the fix
  // history in commit log if you're tempted to refactor.

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

      {!reauthRecent && (
        <form onSubmit={submitReauth} className="mt-4 border border-[hsl(var(--line))] rounded-md p-3 bg-[hsl(var(--background))]" data-testid="passkey-reauth-gate">
          <div className="flex items-center gap-2 text-sm font-medium">
            <Lock size={16} />
            {t("passkey.reauth_title", "Потвърди паролата си, за да управляваш passkeys")}
          </div>
          <p className="text-xs text-[hsl(var(--ink-muted))] mt-1">
            {t("passkey.reauth_subtitle", "Скорошното потвърждаване остава активно за 10 минути.")}
          </p>
          <div className="mt-3 flex flex-col sm:flex-row gap-2">
            <input
              type="password"
              value={reauthPwd}
              onChange={(e) => setReauthPwd(e.target.value)}
              placeholder={t("passkey.password", "Парола")}
              className="flex-1 border border-[hsl(var(--line))] rounded px-3 py-2 text-sm"
              autoComplete="current-password"
              data-testid="passkey-reauth-pwd"
              required
            />
            <button
              type="submit"
              disabled={reauthBusy || !reauthPwd}
              className="btn btn-primary btn-sm"
              data-testid="passkey-reauth-submit"
            >
              {reauthBusy ? t("passkey.verifying", "Проверка...") : t("passkey.confirm", "Потвърди")}
            </button>
          </div>
        </form>
      )}

      {!loading && items.length > 0 && (
        <ul className="mt-4 divide-y divide-[hsl(var(--line))]" data-testid="passkey-list">
          {items.map((c) => {
            const isRenaming = renamingId === c.credential_id;
            const isRemoving = removingId === c.credential_id;
            return (
              <li key={c.credential_id} className="py-3 flex items-center gap-3" data-testid={`passkey-item-${c.credential_id.slice(0, 8)}`}>
                <KeyRound size={18} className="text-[hsl(var(--ink-muted))] shrink-0" />
                <div className="flex-1 min-w-0">
                  {isRenaming ? (
                    <div className="flex items-center gap-2">
                      <input
                        type="text"
                        maxLength={80}
                        value={renameValue}
                        onChange={(e) => setRenameValue(e.target.value)}
                        className="flex-1 border border-[hsl(var(--line))] rounded px-2 py-1 text-sm"
                        autoFocus
                        data-testid={`passkey-rename-input-${c.credential_id.slice(0, 8)}`}
                      />
                      <button
                        onClick={() => submitRename(c.credential_id)}
                        className="text-[hsl(var(--success,#16a34a))] hover:opacity-80"
                        data-testid={`passkey-rename-confirm-${c.credential_id.slice(0, 8)}`}
                      >
                        <Check size={16} />
                      </button>
                      <button
                        onClick={() => { setRenamingId(null); setRenameValue(""); }}
                        className="text-[hsl(var(--ink-muted))] hover:opacity-80"
                      >
                        <X size={16} />
                      </button>
                    </div>
                  ) : (
                    <>
                      <div className="text-sm font-medium truncate">{c.device_name}</div>
                      <div className="text-xs text-[hsl(var(--ink-muted))]">
                        {t("passkey.created", "Добавен")}: {new Date(c.created_at).toLocaleDateString()}
                        {c.last_used_at && (
                          <> · {t("passkey.last_used", "Последно ползван")}: {new Date(c.last_used_at).toLocaleDateString()}</>
                        )}
                      </div>
                    </>
                  )}
                </div>
                {!isRenaming && (
                  <div className="flex items-center gap-2 shrink-0">
                    {isRemoving ? (
                      <>
                        <span className="text-xs text-[hsl(var(--danger))]">{t("passkey.confirm_remove", "Сигурно ли?")}</span>
                        <button
                          onClick={() => confirmRemove(c.credential_id)}
                          className="text-xs text-[hsl(var(--danger))] underline"
                          data-testid={`passkey-confirm-remove-${c.credential_id.slice(0, 8)}`}
                        >
                          {t("common.delete", "Изтрий")}
                        </button>
                        <button
                          onClick={() => setRemovingId(null)}
                          className="text-xs text-[hsl(var(--ink-muted))] underline"
                        >
                          {t("common.cancel", "Откажи")}
                        </button>
                      </>
                    ) : (
                      <>
                        <button
                          type="button"
                          onClick={() => startRename(c)}
                          className="text-xs text-[hsl(var(--ink-muted))] hover:text-[hsl(var(--ink))] flex items-center gap-1"
                          data-testid={`passkey-rename-btn-${c.credential_id.slice(0, 8)}`}
                        >
                          <Pencil size={14} /> {t("common.rename", "Преименувай")}
                        </button>
                        <button
                          type="button"
                          onClick={() => { setRemovingId(c.credential_id); setErr(""); setInfo(""); }}
                          disabled={!reauthRecent}
                          title={!reauthRecent ? t("passkey.reauth_required", "Потвърди паролата първо") : undefined}
                          className="text-xs text-[hsl(var(--ink-muted))] hover:text-[hsl(var(--danger))] flex items-center gap-1 disabled:opacity-40 disabled:cursor-not-allowed"
                          data-testid={`passkey-remove-btn-${c.credential_id.slice(0, 8)}`}
                        >
                          <Trash2 size={14} /> {t("common.remove", "Премахни")}
                        </button>
                      </>
                    )}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {!loading && items.length === 0 && (
        <p className="mt-4 text-sm text-[hsl(var(--ink-muted))]" data-testid="passkey-empty">
          {t("passkey.empty", "Все още нямаш регистрирани passkeys.")}
        </p>
      )}

      <button
        type="button"
        onClick={addPasskey}
        disabled={adding || !reauthRecent}
        title={!reauthRecent ? t("passkey.reauth_required", "Потвърди паролата първо") : undefined}
        className="mt-4 inline-flex items-center gap-2 btn btn-outline btn-sm disabled:opacity-40 disabled:cursor-not-allowed"
        data-testid="passkey-add-btn"
      >
        <Plus size={16} /> {adding ? t("passkey.adding", "Добавяне...") : t("passkey.add", "Добави passkey")}
      </button>
    </section>
  );
}
