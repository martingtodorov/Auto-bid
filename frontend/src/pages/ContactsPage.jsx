import React from "react";
import { useTranslation } from "react-i18next";
import { Mail, Phone, Clock } from "lucide-react";
import InfoPage, { InfoSection } from "../components/InfoPage";
import MarkdownBody from "../components/MarkdownBody";
import HtmlBody from "../components/HtmlBody";
import { useSiteSettings, pickCmsContent, pickCmsHtml } from "../lib/settings";
import { useInfoPageSeo } from "../lib/useInfoPageSeo";
import { useBrandName } from "../lib/brand";

export default function ContactsPage() {
  const { i18n } = useTranslation();
  const brand = useBrandName();
  const settings = useSiteSettings();
  const html = pickCmsHtml(settings, "contacts", i18n.language);
  const custom = pickCmsContent(settings, "contacts_content", i18n.language);
  useInfoPageSeo({
    title: `Контакти — ${brand}`,
    description: `Свържете се с екипа на ${brand} — contact@autoandbid.com, тел. +359 87 827 9269.`,
    path: "/contacts",
    crumb: "Контакти",
  });
  return (
    <InfoPage overline="Помощ" title="Контакти">
      {html ? <HtmlBody html={html} /> : custom ? <MarkdownBody>{custom}</MarkdownBody> : <DefaultContacts />}
    </InfoPage>
  );
}

function DefaultContacts() {
  return (
    <>
      <p className="text-lg text-[hsl(var(--ink-muted))]">Нашият екип отговаря в рамките на 1 работен ден.</p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        <ContactCard icon={Mail} label="Имейл" value="contact@autoandbid.com" href="mailto:contact@autoandbid.com" note="За общи запитвания и поддръжка" />
        <ContactCard icon={Phone} label="Телефон" value="+359 87 827 9269" href="tel:+359878279269" note="Понеделник–Петък · 10:00–17:00" />
        <ContactCard icon={Clock} label="Работно време" value="Пн–Пт: 10:00–17:00" note="Събота и неделя — почивни" />
      </div>
      <InfoSection title="Специализирани запитвания">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          <div className="rounded-card border border-[hsl(var(--line))] bg-white p-5">
            <div className="overline text-[hsl(var(--accent))]">Партньорства и дилъри</div>
            <p className="mt-2 text-sm">Интересувате се от статус „Проверен дилър“ или обемна продажба?</p>
            <a href="mailto:contact@autoandbid.com" className="mt-3 inline-block text-sm font-semibold text-[hsl(var(--accent))] hover:underline">contact@autoandbid.com →</a>
          </div>
          <div className="rounded-card border border-[hsl(var(--line))] bg-white p-5">
            <div className="overline text-[hsl(var(--accent))]">Преса и медии</div>
            <p className="mt-2 text-sm">За интервюта, доклади и статистики.</p>
            <a href="mailto:contact@autoandbid.com" className="mt-3 inline-block text-sm font-semibold text-[hsl(var(--accent))] hover:underline">contact@autoandbid.com →</a>
          </div>
        </div>
      </InfoSection>
    </>
  );
}

function ContactCard({ icon: Icon, label, value, note, href, external }) {
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
  if (href) {
    const extraProps = external ? { target: "_blank", rel: "noopener noreferrer" } : {};
    return <a href={href} className={cls} {...extraProps}>{content}</a>;
  }
  return <div className={cls}>{content}</div>;
}
