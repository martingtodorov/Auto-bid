import React, { useEffect } from "react";
import { useTranslation } from "react-i18next";
import InfoPage, { InfoSection, FAQItem } from "../components/InfoPage";
import MarkdownBody from "../components/MarkdownBody";
import HtmlBody from "../components/HtmlBody";
import { useSiteSettings, pickCmsContent, pickCmsHtml } from "../lib/settings";
import { setPageMeta, resetPageMeta, buildBreadcrumbs, buildFaqJsonLd, combineJsonLd } from "../lib/seo";
import { useBrandName } from "../lib/brand";

/**
 * Build the default QA list from i18n. Each q/a pair lives under `faq.q1..q7`
 * and `faq.a1..a7` — replacing the previous hardcoded BG strings.
 */
function defaultQa(t, pct, brand) {
  return [1, 2, 3, 4, 5, 6, 7].map((i) => ({
    q: t(`faq.q${i}`),
    a: t(`faq.a${i}`, { pct, brand }),
  }));
}

// Simple markdown-like Q/A extractor: expects "## Question?\nAnswer" pairs
function parseFaqMarkdown(md) {
  if (!md) return [];
  const lines = md.split(/\r?\n/);
  const pairs = [];
  let currentQ = null;
  let currentA = [];
  for (const line of lines) {
    const h = line.match(/^#{1,3}\s+(.+)$/);
    if (h) {
      if (currentQ) pairs.push({ q: currentQ, a: currentA.join(" ").trim() });
      currentQ = h[1].trim();
      currentA = [];
    } else if (currentQ) {
      if (line.trim()) currentA.push(line.trim());
    }
  }
  if (currentQ) pairs.push({ q: currentQ, a: currentA.join(" ").trim() });
  return pairs.filter((p) => p.a);
}

export default function FAQPage() {
  const { t, i18n } = useTranslation();
  const brand = useBrandName();
  const settings = useSiteSettings();
  const html = pickCmsHtml(settings, "faq", i18n.language);
  const custom = pickCmsContent(settings, "faq_content", i18n.language);
  const pct = settings?.buyer_fee_pct ?? 2;

  const qa = custom ? parseFaqMarkdown(custom) : defaultQa(t, pct, brand);

  useEffect(() => {
    const url = window.location.origin + "/faq";
    const origin = window.location.origin;
    const lang = (i18n.resolvedLanguage || i18n.language || "bg").slice(0, 2);
    const breadcrumbs = buildBreadcrumbs([
      { name: t("page_meta.home_crumb"), url: origin + "/" },
      { name: t("nav.faq", "FAQ"), url },
    ]);
    const faq = buildFaqJsonLd(qa);
    setPageMeta({
      title: t("page_meta.faq_title", { brand }),
      description: t("page_meta.faq_desc", { brand }),
      url,
      locale: lang,
      jsonLd: combineJsonLd(faq, breadcrumbs),
    });
    return () => resetPageMeta();
  }, [qa.length, pct, brand, t, i18n.language, i18n.resolvedLanguage]);

  return (
    <InfoPage overline={t("info_pages.help_overline")} title={t("nav.faq", "FAQ")}>
      {html ? (
        <HtmlBody html={html} />
      ) : custom ? (
        <MarkdownBody>{custom}</MarkdownBody>
      ) : (
        <>
          <p className="text-lg text-[hsl(var(--ink-muted))]">{t("faq.intro", { brand })}</p>
          <InfoSection title={t("faq.section_bidding")}>
            {defaultQa(t, pct, brand).slice(0, 4).map((it, i) => (
              <FAQItem key={i} q={it.q} a={it.a} />
            ))}
          </InfoSection>
          <InfoSection title={t("faq.section_selling")}>
            {defaultQa(t, pct, brand).slice(4).map((it, i) => (
              <FAQItem key={i} q={it.q} a={it.a} />
            ))}
          </InfoSection>
        </>
      )}
    </InfoPage>
  );
}
