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
  const { t, i18n } = useTranslation();
  const brand = useBrandName();
  const settings = useSiteSettings();
  const html = pickCmsHtml(settings, "contacts", i18n.language);
  const custom = pickCmsContent(settings, "contacts_content", i18n.language);
  useInfoPageSeo({
    title: t("page_meta.contacts_title", { brand }),
    description: t("page_meta.contacts_desc", { brand }),
    path: "/contacts",
    crumb: t("nav.contacts", "Contacts"),
  });
  return (
    <InfoPage overline={t("info_pages.help_overline")} title={t("nav.contacts", "Contacts")}>
      {html ? <HtmlBody html={html} /> : custom ? <MarkdownBody>{custom}</MarkdownBody> : <DefaultContacts t={t} />}
    </InfoPage>
  );
}

function DefaultContacts({ t }) {
  return (
    <>
      <p className="text-lg text-[hsl(var(--ink-muted))]">{t("contacts.intro")}</p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        <ContactCard icon={Mail} label={t("contacts.email_label")} value="contact@autoandbid.com" href="mailto:contact@autoandbid.com" note={t("contacts.email_note")} />
        <ContactCard icon={Phone} label={t("contacts.phone_label")} value="+359 87 827 9269" href="tel:+359878279269" note={t("contacts.phone_note")} />
        <ContactCard icon={Clock} label={t("contacts.hours_label")} value={t("contacts.hours_value")} note={t("contacts.hours_note")} />
      </div>
      <InfoSection title={t("contacts.specialized_title")}>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          <div className="rounded-card border border-[hsl(var(--line))] bg-white p-5">
            <div className="overline text-[hsl(var(--accent))]">{t("contacts.partners_overline")}</div>
            <p className="mt-2 text-sm">{t("contacts.partners_body")}</p>
            <a href="mailto:contact@autoandbid.com" className="mt-3 inline-block text-sm font-semibold text-[hsl(var(--accent))] hover:underline">contact@autoandbid.com →</a>
          </div>
          <div className="rounded-card border border-[hsl(var(--line))] bg-white p-5">
            <div className="overline text-[hsl(var(--accent))]">{t("contacts.press_overline")}</div>
            <p className="mt-2 text-sm">{t("contacts.press_body")}</p>
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
