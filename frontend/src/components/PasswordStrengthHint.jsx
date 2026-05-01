import React from "react";
import { useTranslation } from "react-i18next";
import { Check, X } from "lucide-react";

/**
 * Live password complexity feedback. Mirrors the server-side rules in
 * `services/password_security.py`:
 *   - 8+ characters
 *   - at least 1 uppercase letter
 *   - at least 1 digit OR symbol
 *
 * Pure presentational — never blocks submit; the form's native `minLength`
 * + server-side validation are the source of truth.
 */
export default function PasswordStrengthHint({ password = "" }) {
  const { t } = useTranslation();

  const rules = [
    {
      key: "len",
      ok: password.length >= 8,
      label: t("auth.pw_rule_len", "Поне 8 символа"),
    },
    {
      key: "upper",
      ok: /[A-Z]/.test(password),
      label: t("auth.pw_rule_upper", "Поне една главна буква"),
    },
    {
      key: "digit_sym",
      ok: /[0-9!@#$%^&*()_\-+=\[\]{};:'",.<>/?\\|`~]/.test(password),
      label: t("auth.pw_rule_digit", "Поне една цифра или специален символ"),
    },
  ];

  const allOk = rules.every((r) => r.ok);

  return (
    <ul
      className={`mt-2 space-y-1 text-xs ${
        allOk ? "text-[hsl(var(--accent))]" : "text-[hsl(var(--ink-muted))]"
      }`}
      data-testid="password-strength"
    >
      {rules.map((r) => (
        <li key={r.key} className="flex items-center gap-1.5">
          {r.ok ? (
            <Check size={12} className="text-[hsl(var(--accent))]" />
          ) : (
            <X size={12} className="text-[hsl(var(--ink-muted))] opacity-60" />
          )}
          <span className={r.ok ? "text-[hsl(var(--ink))]" : ""}>{r.label}</span>
        </li>
      ))}
    </ul>
  );
}
