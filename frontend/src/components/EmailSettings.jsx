import React from "react";
import { useTranslation } from "react-i18next";
import { Mail } from "lucide-react";
import NotificationToggles from "./NotificationToggles";

/**
 * Email notification preferences card.
 *
 * Mirrors `PushSettings` for the email channel — the user always has email
 * (vs needing to subscribe to push), so there's no enable/disable button
 * here, just per-event toggles.
 */
export default function EmailSettings() {
  const { t } = useTranslation();
  return (
    <section
      className="rounded-card border border-[hsl(var(--line))] p-5 sm:p-6 bg-[hsl(var(--surface))]"
      data-testid="email-settings"
    >
      <header className="flex items-start gap-3 mb-3">
        <div className="w-10 h-10 rounded-full bg-[hsl(var(--accent-soft))] text-[hsl(var(--accent))] flex items-center justify-center">
          <Mail size={18} />
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="font-serif text-lg">{t("email_prefs.title", "Имейл известия")}</h3>
          <p className="text-sm text-[hsl(var(--ink-muted))] mt-1">
            {t(
              "email_prefs.description",
              "Получавайте имейли за важни събития: надминаване, наддавания по обявите ви, нови коли по запазени търсения и още."
            )}
          </p>
        </div>
      </header>

      <div className="mt-4 pt-4 border-t border-[hsl(var(--line))]">
        <p className="text-xs uppercase tracking-wider text-[hsl(var(--ink-muted))] mb-1">
          {t("notif_prefs.section", "Какво да получавате")}
        </p>
        <NotificationToggles channel="email" />
      </div>
    </section>
  );
}
