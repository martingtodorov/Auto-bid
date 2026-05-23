import React from "react";
import { useTranslation } from "react-i18next";
import InfoPage, { InfoSection } from "../components/InfoPage";
import MarkdownBody from "../components/MarkdownBody";
import HtmlBody from "../components/HtmlBody";
import { useSiteSettings, pickCmsContent, pickCmsHtml } from "../lib/settings";
import { useInfoPageSeo } from "../lib/useInfoPageSeo";
import { useBrandName } from "../lib/brand";

export default function TermsPage() {
  const { t, i18n } = useTranslation();
  const brand = useBrandName();
  const settings = useSiteSettings();
  const html = pickCmsHtml(settings, "terms", i18n.language);
  const custom = pickCmsContent(settings, "terms_content", i18n.language);
  useInfoPageSeo({
    title: t("page_meta.terms_title", { brand }),
    description: t("page_meta.terms_desc", { brand }),
    path: "/terms",
    crumb: t("nav.terms", "Terms"),
  });
  return (
    <InfoPage overline={t("info_pages.legal_overline")} title={t("nav.terms", "Terms")}>
      {html ? (
        <HtmlBody html={html} />
      ) : custom ? (
        <MarkdownBody>{custom}</MarkdownBody>
      ) : (
        <DefaultTerms pct={settings?.buyer_fee_pct ?? 2} brand={brand} t={t} />
      )}
    </InfoPage>
  );
}

function DefaultTerms({ pct, brand, t }) {
  return (
    <>
      <p className="text-sm text-[hsl(var(--ink-muted))]">{t("terms.last_updated")}</p>
      <InfoSection title={t("terms.s1_title")}>
        <p>{t("terms.s1_body", { brand })}</p>
      </InfoSection>
      <InfoSection title={t("terms.s2_title")}>
        <p>{t("terms.s2_body")}</p>
      </InfoSection>
      <InfoSection title={t("terms.s3_title")}>
        <p>{t("terms.s3_body", { pct })}</p>
      </InfoSection>
      <InfoSection title={t("terms.s4_title")}>
        <p>{t("terms.s4_body")}</p>
      </InfoSection>
      <InfoSection title={t("terms.s5_title")}>
        <p>{t("terms.s5_body", { brand })}</p>
      </InfoSection>
      <InfoSection title={t("terms.s6_title")}>
        <p>
          {t("terms.s6_body_prefix")}
          <a href="mailto:contact@autoandbid.com" className="text-[hsl(var(--accent))] hover:underline">contact@autoandbid.com</a>
          {t("terms.s6_body_suffix")}
        </p>
      </InfoSection>
    </>
  );
}
