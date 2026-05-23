import React from "react";
import { useTranslation } from "react-i18next";
import InfoPage, { InfoSection } from "../components/InfoPage";
import MarkdownBody from "../components/MarkdownBody";
import HtmlBody from "../components/HtmlBody";
import { useSiteSettings, pickCmsContent, pickCmsHtml } from "../lib/settings";
import { useInfoPageSeo } from "../lib/useInfoPageSeo";
import { useBrandName } from "../lib/brand";

export default function FeesPage() {
  const { t, i18n } = useTranslation();
  const brand = useBrandName();
  const settings = useSiteSettings();
  const html = pickCmsHtml(settings, "fees", i18n.language);
  const custom = pickCmsContent(settings, "fees_content", i18n.language);
  const pct = settings?.buyer_fee_pct ?? 2;
  const min = settings?.buyer_fee_min_eur ?? 150;
  const max = settings?.buyer_fee_max_eur ?? 4000;
  useInfoPageSeo({
    title: t("page_meta.fees_title", { brand }),
    description: t("page_meta.fees_desc", { brand }),
    path: "/fees",
    crumb: t("nav.fees", "Fees"),
  });
  return (
    <InfoPage overline={t("info_pages.help_overline")} title={t("nav.fees", "Fees")}>
      {html ? (
        <HtmlBody html={html} />
      ) : custom ? (
        <MarkdownBody>{custom}</MarkdownBody>
      ) : (
        <DefaultFees pct={pct} min={min} max={max} t={t} />
      )}
    </InfoPage>
  );
}

function DefaultFees({ pct, min, max, t }) {
  const exampleFee = Math.min(max, Math.max(min, Math.round(20000 * pct / 100)));
  return (
    <>
      <p className="text-lg text-[hsl(var(--ink-muted))]">{t("fees.intro")}</p>
      <InfoSection title={t("fees.buyers_title")}>
        <div className="rounded-card border border-[hsl(var(--line))] bg-white p-6">
          <div className="overline text-[hsl(var(--accent))]">{t("fees.buyers_overline")}</div>
          <div className="font-serif text-4xl mt-2">{pct}%</div>
          <p className="mt-3 text-[hsl(var(--ink-muted))]">{t("fees.buyers_body", { min, max })}</p>
          <p className="mt-3 text-xs text-[hsl(var(--ink-muted))]">{t("fees.buyers_example", { fee: exampleFee })}</p>
        </div>
      </InfoSection>
      <InfoSection title={t("fees.sellers_title")}>
        <div className="rounded-card border border-[hsl(var(--accent))]/30 bg-[hsl(var(--accent-soft))] p-6">
          <div className="overline text-[hsl(var(--accent))]">{t("fees.sellers_overline")}</div>
          <div className="font-serif text-4xl mt-2">0 €</div>
          <p className="mt-3 text-[hsl(var(--ink))]/80 leading-relaxed">{t("fees.sellers_body")}</p>
        </div>
      </InfoSection>
    </>
  );
}
