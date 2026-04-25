import React, { useEffect, useState } from "react";
import { Bell, BellOff, AlertCircle, Smartphone } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  pushSupported,
  pushAvailableHere,
  isIOS,
  isStandalone,
  getCurrentSubscription,
  subscribePush,
  unsubscribePush,
  sendTestPush,
} from "../lib/push";

/**
 * Settings card for Web Push notifications.
 *
 * States:
 *  - unsupported  → explainer (e.g. iOS without PWA install)
 *  - default      → "Enable notifications" button
 *  - granted+sub  → "Disable" + "Send test"
 *  - denied       → reset instructions
 */
export default function PushSettings() {
  const { t } = useTranslation();
  const [status, setStatus] = useState("loading"); // loading|unsupported|ios-pwa-needed|default|denied|subscribed
  const [working, setWorking] = useState(false);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  const refresh = async () => {
    if (!pushSupported()) {
      setStatus("unsupported");
      return;
    }
    if (isIOS() && !isStandalone()) {
      setStatus("ios-pwa-needed");
      return;
    }
    if (Notification.permission === "denied") {
      setStatus("denied");
      return;
    }
    const sub = await getCurrentSubscription();
    setStatus(sub ? "subscribed" : "default");
  };

  useEffect(() => {
    refresh();
  }, []);

  const enable = async () => {
    setWorking(true);
    setErr("");
    setMsg("");
    try {
      await subscribePush();
      setMsg(t("push.enabled_msg", "Известията са включени."));
      await refresh();
    } catch (e) {
      setErr(e.message || String(e));
    } finally {
      setWorking(false);
    }
  };

  const disable = async () => {
    setWorking(true);
    setErr("");
    setMsg("");
    try {
      await unsubscribePush();
      setMsg(t("push.disabled_msg", "Известията са спрени."));
      await refresh();
    } catch (e) {
      setErr(e.message || String(e));
    } finally {
      setWorking(false);
    }
  };

  const test = async () => {
    setWorking(true);
    setErr("");
    setMsg("");
    try {
      await sendTestPush();
      setMsg(t("push.test_sent", "Тестовото известие е изпратено. Проверете телефона/браузъра си."));
    } catch (e) {
      setErr(e.message || String(e));
    } finally {
      setWorking(false);
    }
  };

  return (
    <section
      className="rounded-card border border-[hsl(var(--line))] p-5 sm:p-6 bg-[hsl(var(--surface))]"
      data-testid="push-settings"
    >
      <header className="flex items-start gap-3 mb-4">
        <div className="w-10 h-10 rounded-full bg-[hsl(var(--accent-soft))] text-[hsl(var(--accent))] flex items-center justify-center">
          <Bell size={18} />
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="font-serif text-lg">{t("push.title", "Push известия")}</h3>
          <p className="text-sm text-[hsl(var(--ink-muted))] mt-1">
            {t(
              "push.description",
              "Получавайте известия в реално време когато бъдете надминати, ваша обява получи наддаване или нова кола съответства на запазено търсене."
            )}
          </p>
        </div>
      </header>

      <ul className="text-sm text-[hsl(var(--ink-muted))] space-y-1.5 mb-5 list-disc pl-5">
        <li>{t("push.bullet_outbid", "Надминати сте от друг купувач")}</li>
        <li>{t("push.bullet_seller", "Ваш автомобил получи наддаване")}</li>
        <li>{t("push.bullet_saved", "Нова обява съответства на запазено търсене")}</li>
      </ul>

      {status === "loading" && (
        <p className="text-sm text-[hsl(var(--ink-muted))]">…</p>
      )}

      {status === "unsupported" && (
        <div className="flex items-start gap-2 text-sm text-[hsl(var(--ink-muted))]" data-testid="push-unsupported">
          <AlertCircle size={16} className="shrink-0 mt-0.5" />
          <p>
            {t(
              "push.unsupported",
              "Този браузър не поддържа push известия. Опитайте с Chrome, Edge, Firefox или Safari (iOS 16.4+)."
            )}
          </p>
        </div>
      )}

      {status === "ios-pwa-needed" && (
        <div className="flex items-start gap-2 text-sm text-[hsl(var(--ink-muted))]" data-testid="push-ios-needed">
          <Smartphone size={16} className="shrink-0 mt-0.5" />
          <p>
            {t(
              "push.ios_install",
              'На iPhone/iPad: натиснете бутона "Сподели" в Safari → "Add to Home Screen". След това отворете приложението от началния екран и включете известията тук.'
            )}
          </p>
        </div>
      )}

      {status === "denied" && (
        <div className="flex items-start gap-2 text-sm text-[hsl(var(--danger))]" data-testid="push-denied">
          <AlertCircle size={16} className="shrink-0 mt-0.5" />
          <p>
            {t(
              "push.denied",
              "Известията са блокирани в браузъра. Разрешете ги от настройките на сайта (иконата на катинар в адресната лента) и опитайте отново."
            )}
          </p>
        </div>
      )}

      {status === "default" && (
        <button
          onClick={enable}
          disabled={working}
          className="btn btn-primary"
          data-testid="push-enable-btn"
        >
          <Bell size={16} className="mr-2" />
          {working ? t("common.loading", "…") : t("push.enable", "Включи известията")}
        </button>
      )}

      {status === "subscribed" && (
        <div className="flex flex-wrap gap-2">
          <button
            onClick={disable}
            disabled={working}
            className="btn btn-secondary"
            data-testid="push-disable-btn"
          >
            <BellOff size={16} className="mr-2" />
            {t("push.disable", "Спри известията")}
          </button>
          <button
            onClick={test}
            disabled={working}
            className="btn btn-secondary"
            data-testid="push-test-btn"
          >
            {t("push.send_test", "Изпрати тест")}
          </button>
        </div>
      )}

      {msg && <p className="text-sm text-[hsl(var(--accent))] mt-3" data-testid="push-msg">{msg}</p>}
      {err && <p className="text-sm text-[hsl(var(--danger))] mt-3" data-testid="push-err">{err}</p>}
    </section>
  );
}
