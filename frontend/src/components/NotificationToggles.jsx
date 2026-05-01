import React, { useEffect, useState, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../lib/apiClient";
import { useAuth } from "../lib/auth";

export const NOTIF_KINDS = [
  "outbid",
  "seller_new_bid",
  "saved_search",
  "ending_soon",
  "reserve_met",
];

const DEFAULT_PREFS = {
  push: Object.fromEntries(NOTIF_KINDS.map((k) => [k, true])),
  email: Object.fromEntries(NOTIF_KINDS.map((k) => [k, true])),
};

/**
 * Standalone toggle list for one channel (push or email).
 *
 * Usage:
 *   <NotificationToggles channel="push"  disabled={!subscribed} />
 *   <NotificationToggles channel="email" />
 *
 * The component reads the user's current prefs from `useAuth().user`,
 * persists toggle changes via PATCH /api/me/profile and refreshes auth
 * state on success.
 */
export default function NotificationToggles({ channel = "push", disabled = false }) {
  const { t } = useTranslation();
  const { user, refresh } = useAuth();
  const [prefs, setPrefs] = useState(() => ({ ...DEFAULT_PREFS[channel] }));
  const [saving, setSaving] = useState(null); // current kind being saved
  const [err, setErr] = useState("");

  // Hydrate from user
  useEffect(() => {
    if (!user) return;
    const fromServer = user.notification_prefs?.[channel] || {};
    setPrefs({
      ...DEFAULT_PREFS[channel],
      ...fromServer,
    });
  }, [user, channel]);

  const toggle = useCallback(
    async (kind) => {
      if (disabled) return;
      const next = !prefs[kind];
      setPrefs((p) => ({ ...p, [kind]: next }));
      setSaving(kind);
      setErr("");
      try {
        await api.patch("/me/profile", {
          notification_prefs: { [channel]: { [kind]: next } },
        });
        try { await refresh(); } catch (_e) { /* noop */ }
      } catch (e) {
        // Revert on failure
        setPrefs((p) => ({ ...p, [kind]: !next }));
        setErr(e?.response?.data?.detail || t("notif_prefs.save_err", "Грешка при запис"));
      } finally {
        setSaving(null);
      }
    },
    [prefs, channel, disabled, refresh, t]
  );

  if (!user) return null;

  return (
    <ul
      className="mt-3 space-y-2.5"
      data-testid={`notif-toggles-${channel}`}
    >
      {NOTIF_KINDS.map((kind) => (
        <li
          key={kind}
          className="flex items-center justify-between gap-3 py-1"
        >
          <span className="text-sm text-[hsl(var(--ink))] flex-1 min-w-0">
            {t(`notif_prefs.kinds.${kind}`)}
          </span>
          <button
            type="button"
            role="switch"
            aria-checked={prefs[kind]}
            disabled={disabled || saving === kind}
            onClick={() => toggle(kind)}
            className={`relative shrink-0 w-11 h-6 rounded-full transition-colors duration-200 ${
              prefs[kind]
                ? "bg-[hsl(var(--accent))]"
                : "bg-[hsl(var(--line))]"
            } disabled:opacity-50`}
            data-testid={`notif-toggle-${channel}-${kind}`}
          >
            <span
              className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow-sm transition-transform duration-200 ${
                prefs[kind] ? "translate-x-5" : "translate-x-0"
              }`}
            />
          </button>
        </li>
      ))}
      {err && (
        <li className="text-xs text-[hsl(var(--danger))]" data-testid={`notif-err-${channel}`}>
          {err}
        </li>
      )}
    </ul>
  );
}
