import React from "react";
import { useTranslation } from "react-i18next";
import InfoPage, { InfoSection } from "../components/InfoPage";
import MarkdownBody from "../components/MarkdownBody";
import HtmlBody from "../components/HtmlBody";
import { useSiteSettings, pickCmsContent, pickCmsHtml } from "../lib/settings";
import { useInfoPageSeo } from "../lib/useInfoPageSeo";
import { useBrandName } from "../lib/brand";

export default function TermsPage() {
  const { i18n } = useTranslation();
  const brand = useBrandName();
  const settings = useSiteSettings();
  const html = pickCmsHtml(settings, "terms", i18n.language);
  const custom = pickCmsContent(settings, "terms_content", i18n.language);
  useInfoPageSeo({
    title: `Общи условия — ${brand}`,
    description: `Общите условия за ползване на платформата ${brand} — права, задължения на продавачи и купувачи.`,
    path: "/terms",
    crumb: "Общи условия",
  });
  return (
    <InfoPage overline="Правна информация" title="Общи условия">
      {html ? (
        <HtmlBody html={html} />
      ) : custom ? (
        <MarkdownBody>{custom}</MarkdownBody>
      ) : (
        <DefaultTerms pct={settings?.buyer_fee_pct ?? 2} brand={brand} />
      )}
    </InfoPage>
  );
}

function DefaultTerms({ pct, brand }) {
  return (
    <>
      <p className="text-sm text-[hsl(var(--ink-muted))]">Последна актуализация: 15 февруари 2026 г.</p>
      <InfoSection title="1. Обхват и предмет">
        <p>Настоящите общи условия уреждат отношенията между „{brand}“ и потребителите — купувачи и продавачи, участващи в онлайн търгове за моторни превозни средства.</p>
      </InfoSection>
      <InfoSection title="2. Регистрация">
        <p>Регистрацията е безплатна. Потребителят гарантира истинността на предоставените лични данни.</p>
      </InfoSection>
      <InfoSection title="3. Търгове и наддаване">
        <p>Всяка активна обява е договорно обвързваща. Наддаването представлява неотменима оферта за покупка на обявената цена плюс {pct}% buyer's premium. Pre-authorization от {pct}% се блокира на картата на наддавача при всяка нова оферта.</p>
      </InfoSection>
      <InfoSection title="4. Продавачи и обяви">
        <p>Обявите се одобряват от редакцията в рамките на 48 часа. Резервна цена (по избор) не е задължителна.</p>
      </InfoSection>
      <InfoSection title="5. Сделка и предаване">
        <p>Плащането между купувача и продавача се извършва директно — банков превод или ескроу. {brand} не съхранява средствата на сделката.</p>
      </InfoSection>
      <InfoSection title="6. Контакти и спорове">
        <p>За въпроси: <a href="mailto:contact@autoandbid.com" className="text-[hsl(var(--accent))] hover:underline">contact@autoandbid.com</a>. Компетентен е Софийски районен съд.</p>
      </InfoSection>
    </>
  );
}
