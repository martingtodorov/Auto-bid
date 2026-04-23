import React from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Shield, FileCheck, Gavel, Sparkles } from "lucide-react";
import InfoPage from "../components/InfoPage";
import MarkdownBody from "../components/MarkdownBody";
import { useSiteSettings, pickCmsContent } from "../lib/settings";
import { useInfoPageSeo } from "../lib/useInfoPageSeo";
import { useBrandName } from "../lib/brand";

export default function HowItWorksPage() {
  const { t, i18n } = useTranslation();
  const brand = useBrandName();
  const settings = useSiteSettings();
  const custom = pickCmsContent(settings, "how_it_works_content", i18n.language);
  useInfoPageSeo({
    title: `${t("nav.how_it_works", "Как работи")} — ${brand}`,
    description: t("how_it_works.intro_body", { brand }),
    path: "/how-it-works",
    crumb: t("nav.how_it_works", "Как работи"),
  });
  if (custom) {
    return (
      <InfoPage overline={t("how_it_works.overline")} title={t("nav.how_it_works", "Как работи")}>
        <MarkdownBody>{custom}</MarkdownBody>
      </InfoPage>
    );
  }
  return <DefaultHowItWorks pct={settings?.buyer_fee_pct ?? 2} brand={brand} t={t} />;
}

function DefaultHowItWorks({ pct, brand, t }) {
  const steps = [
    { n: "01", i: Shield, t: t("how_it_works.step_01_t"), d: t("how_it_works.step_01_d") },
    { n: "02", i: FileCheck, t: t("how_it_works.step_02_t"), d: t("how_it_works.step_02_d") },
    { n: "03", i: Gavel, t: t("how_it_works.step_03_t"), d: t("how_it_works.step_03_d") },
    { n: "04", i: Sparkles, t: t("how_it_works.step_04_t"), d: t("how_it_works.step_04_d") },
  ];
  return (
    <main data-testid="how-it-works-page">
      <section className="rule-b">
        <div className="max-w-[1200px] mx-auto px-4 sm:px-6 lg:px-10 py-20 lg:py-28 text-center">
          <div className="overline text-[hsl(var(--accent))]">{t("how_it_works.overline")}</div>
          <h1 className="hero-headline text-5xl lg:text-7xl mt-5">
            {t("how_it_works.hero_headline_1")}<br/><em>{t("how_it_works.hero_headline_2")}</em>
          </h1>
          <p className="mt-8 text-lg text-[hsl(var(--ink-muted))] max-w-2xl mx-auto leading-relaxed">
            {t("how_it_works.intro_body", { brand })}
          </p>
        </div>
      </section>

      <section className="rule-b bg-[hsl(var(--surface))]">
        <div className="max-w-[1200px] mx-auto px-4 sm:px-6 lg:px-10 py-16 lg:py-24">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-0 border border-[hsl(var(--line))] bg-white">
            {steps.map((s, i) => (
              <div key={i} className="p-10 rule-b md:border-r md:border-[hsl(var(--line))] md:[&:nth-child(2n)]:border-r-0 md:[&:nth-last-child(-n+2)]:border-b-0">
                <div className="font-mono text-xs text-[hsl(var(--accent))]">{s.n}</div>
                <s.i size={28} className="mt-4 text-[hsl(var(--ink))]" />
                <h3 className="font-serif text-2xl mt-5">{s.t}</h3>
                <p className="mt-3 text-sm text-[hsl(var(--ink-muted))] leading-relaxed">{s.d}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id="fees" className="rule-b">
        <div className="max-w-[1200px] mx-auto px-4 sm:px-6 lg:px-10 py-16 lg:py-24">
          <div className="overline text-[hsl(var(--accent))]">{t("how_it_works.fees_overline")}</div>
          <h2 className="font-serif text-3xl lg:text-5xl mt-3">{t("how_it_works.fees_title")}</h2>
          <div className="mt-10 grid grid-cols-1 md:grid-cols-3 gap-0 border border-[hsl(var(--line))]">
            <div className="p-8 border-b md:border-b-0 md:border-r border-[hsl(var(--line))]">
              <div className="overline text-[hsl(var(--ink-muted))]">{t("how_it_works.fee_buyer")}</div>
              <div className="font-serif text-5xl mt-3">{pct}%</div>
              <p className="mt-3 text-sm text-[hsl(var(--ink-muted))]">{t("how_it_works.fee_buyer_body", { pct })}</p>
            </div>
            <div className="p-8 border-b md:border-b-0 md:border-r border-[hsl(var(--line))]">
              <div className="overline text-[hsl(var(--ink-muted))]">{t("how_it_works.fee_seller")}</div>
              <div className="font-serif text-5xl mt-3">€0</div>
              <p className="mt-3 text-sm text-[hsl(var(--ink-muted))]">{t("how_it_works.fee_seller_body")}</p>
            </div>
            <div className="p-8">
              <div className="overline text-[hsl(var(--ink-muted))]">{t("how_it_works.fee_failed")}</div>
              <div className="font-serif text-5xl mt-3">€0</div>
              <p className="mt-3 text-sm text-[hsl(var(--ink-muted))]">{t("how_it_works.fee_failed_body")}</p>
            </div>
          </div>
        </div>
      </section>

      <section className="bg-[hsl(var(--ink))] text-white">
        <div className="max-w-[1200px] mx-auto px-4 sm:px-6 lg:px-10 py-20 flex flex-col md:flex-row items-center justify-between gap-8">
          <h2 className="hero-headline text-4xl lg:text-5xl">{t("how_it_works.cta_title")}</h2>
          <Link to="/register" className="btn !border-white bg-white !text-[hsl(var(--ink))] hover:!bg-[hsl(var(--accent))] hover:!text-white hover:!border-[hsl(var(--accent))]">{t("how_it_works.cta_btn")}</Link>
        </div>
      </section>
    </main>
  );
}
