import React from "react";
import { Mail, Phone, MapPin, Clock } from "lucide-react";
import InfoPage, { InfoSection } from "../components/InfoPage";
import MarkdownBody from "../components/MarkdownBody";
import { useSiteSettings } from "../lib/settings";
import { useInfoPageSeo } from "../lib/useInfoPageSeo";

export default function ContactsPage() {
  const settings = useSiteSettings();
  const custom = settings?.contacts_content?.trim();
  useInfoPageSeo({
    title: "Контакти — autobids.bg",
    description: "Свържете се с екипа на autobids.bg — имейл contact@autobids.bg, телефон +359 2 444 2828, София.",
    path: "/contacts",
    crumb: "Контакти",
  });
  return (
    <InfoPage overline="Помощ" title="Контакти">
      {custom ? <MarkdownBody>{custom}</MarkdownBody> : <DefaultContacts />}
    </InfoPage>
  );
}

function DefaultContacts() {
  return (
    <>
      <p className="text-lg text-[hsl(var(--ink-muted))]">Нашият екип отговаря в рамките на 1 работен ден.</p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        <ContactCard icon={Mail} label="Имейл" value="contact@autobids.bg" href="mailto:contact@autobids.bg" note="За общи запитвания и поддръжка" />
        <ContactCard icon={Phone} label="Телефон" value="+359 2 444 2828" href="tel:+35924442828" note="Понеделник–Петък · 9:00–18:00" />
        <ContactCard icon={MapPin} label="Адрес" value="ул. Шишман 18, 1000 София" note="Срещи по предварителна уговорка" />
        <ContactCard icon={Clock} label="Работно време" value="Пн–Пт: 9:00–18:00" note="Съб: 10:00–14:00 (само онлайн)" />
      </div>
      <InfoSection title="Специализирани запитвания">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          <div className="rounded-card border border-[hsl(var(--line))] bg-white p-5">
            <div className="overline text-[hsl(var(--accent))]">Партньорства и дилъри</div>
            <p className="mt-2 text-sm">Интересувате се от статус „Проверен дилър“ или обемна продажба?</p>
            <a href="mailto:dealers@autobids.bg" className="mt-3 inline-block text-sm font-semibold text-[hsl(var(--accent))] hover:underline">dealers@autobids.bg →</a>
          </div>
          <div className="rounded-card border border-[hsl(var(--line))] bg-white p-5">
            <div className="overline text-[hsl(var(--accent))]">Преса и медии</div>
            <p className="mt-2 text-sm">За интервюта, доклади и статистики.</p>
            <a href="mailto:press@autobids.bg" className="mt-3 inline-block text-sm font-semibold text-[hsl(var(--accent))] hover:underline">press@autobids.bg →</a>
          </div>
        </div>
      </InfoSection>
    </>
  );
}

function ContactCard({ icon: Icon, label, value, note, href }) {
  const content = (
    <>
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-full bg-[hsl(var(--accent-soft))] flex items-center justify-center text-[hsl(var(--accent))]">
          <Icon size={18} />
        </div>
        <div className="overline text-[hsl(var(--ink-muted))]">{label}</div>
      </div>
      <div className="mt-3 font-serif text-xl">{value}</div>
      {note && <div className="mt-1 text-xs text-[hsl(var(--ink-muted))]">{note}</div>}
    </>
  );
  const cls = "block rounded-card border border-[hsl(var(--line))] bg-white p-5 transition hover:border-[hsl(var(--accent))]";
  return href ? <a href={href} className={cls}>{content}</a> : <div className={cls}>{content}</div>;
}
