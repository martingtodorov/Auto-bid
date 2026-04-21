import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowRight, Shield, Gavel, FileCheck, Sparkles } from "lucide-react";
import { api, formatEUR, formatLocal } from "../lib/apiClient";
import AuctionCard from "../components/AuctionCard";
import { setPageMeta, resetPageMeta } from "../lib/seo";
import { useSiteSettings } from "../lib/settings";
import { translateEnum } from "../lib/carTranslations";

const HERO_IMAGE = "https://images.unsplash.com/photo-1698995339730-86b3dd454001?crop=entropy&cs=srgb&fm=jpg&q=85&w=2000";

export default function LandingPage() {
  const { t, i18n } = useTranslation();
  const [auctions, setAuctions] = useState([]);
  const [featured, setFeatured] = useState([]);
  const [sold, setSold] = useState([]);
  const settings = useSiteSettings();

  // Update SEO from site settings
  useEffect(() => {
    if (settings?.seo_title || settings?.seo_description) {
      setPageMeta({
        title: settings.seo_title,
        description: settings.seo_description,
        url: window.location.origin,
      });
    }
    return () => resetPageMeta();
  }, [settings?.seo_title, settings?.seo_description]);

  useEffect(() => {
    (async () => {
      try {
        const [l, f, s] = await Promise.all([
          api.get("/auctions", { params: { sort: "ending_soon", status: "live", limit: 6 } }),
          api.get("/auctions/featured"),
          api.get("/auctions/sold"),
        ]);
        setAuctions(l.data);
        setFeatured(f.data);
        setSold(s.data);
      } catch (e) {
        console.error(e);
      }
    })();
  }, []);

  const hero = featured[0] || auctions[0];

  // CMS-editable hero text per language (falls back to static i18n)
  const lang = (i18n.resolvedLanguage || "bg").slice(0, 2);
  const cmsHeadline = settings?.[`hero_headline_${lang}`];
  const cmsSubtitle = settings?.[`hero_subtitle_${lang}`];

  return (
    <main data-testid="landing-page">
      {/* Hero */}
      <section className="rule-b hero-ambient">
        <div className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-10 py-6 lg:py-3">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 lg:gap-12 items-center">
            <div className="lg:col-span-6 fade-up">
              {cmsHeadline ? (
                <h1
                  className="hero-headline text-5xl sm:text-6xl lg:text-[60px] lg:leading-[1.05] mt-0"
                  data-testid="hero-headline-cms"
                  dangerouslySetInnerHTML={{ __html: cmsHeadline.replace(/\n/g, "<br />") }}
                />
              ) : (
                <h1 className="hero-headline text-5xl sm:text-6xl lg:text-[60px] lg:leading-[1.05] mt-0 text-balance" data-testid="hero-headline-i18n">
                  {t("hero.discover")} <em>{t("hero.exceptional")}</em> {t("hero.cars")}
                </h1>
              )}
              <p className="mt-5 text-base lg:text-lg text-[hsl(var(--ink-muted))] leading-relaxed max-w-xl" data-testid="hero-subtitle">
                {cmsSubtitle || t("hero.subtitle")}
              </p>
              <div className="mt-6 flex flex-wrap gap-3">
                <Link to="/auctions" className="btn btn-primary !px-10" data-testid="hero-cta-browse">
                  {t("hero.browse")} <ArrowRight size={16} className="ml-2" />
                </Link>
                <Link to="/sell" className="btn btn-sell-gradient !px-10" data-testid="hero-cta-sell">
                  {t("hero.sell_cta")}
                </Link>
              </div>
            </div>

            <div className="lg:col-span-6 fade-up">
              {hero ? (
                <Link to={`/auctions/${hero.id}`} className="block group" data-testid="hero-featured-auction">
                  <div className="aspect-[4/3] lg:aspect-[16/10] overflow-hidden rounded-card border border-[hsl(var(--line))]">
                    <img src={hero.images?.[0] || HERO_IMAGE} alt={hero.title} className="w-full h-full object-cover transition-transform duration-700 group-hover:scale-105" />
                  </div>
                  <div className="mt-3 flex items-end justify-between gap-4">
                    <div>
                      <div className="overline text-[hsl(var(--accent))]">{t("hero.featured_listing")}</div>
                      <h3 className="font-serif text-xl lg:text-2xl mt-1.5 tracking-tight">{hero.title}</h3>
                      <div className="text-sm text-[hsl(var(--ink-muted))] mt-1.5">
                        {hero.year} · {translateEnum(hero.city, "city", i18n.language)} · {translateEnum(hero.fuel, "fuel", i18n.language)}
                      </div>
                    </div>
                    <div className="text-right shrink-0">
                      <div className="overline text-[hsl(var(--ink-muted))]">{t("hero.current")}</div>
                      <div className="font-serif text-xl lg:text-2xl">{formatEUR(hero.current_bid_eur)}</div>
                      <div className="text-xs font-mono text-[hsl(var(--ink-muted))]">{formatLocal(hero.current_bid_eur, i18n.language)}</div>
                    </div>
                  </div>
                </Link>
              ) : (
                <div className="aspect-[4/3] lg:aspect-[16/10] border border-[hsl(var(--line))] bg-[hsl(var(--surface))]" />
              )}
            </div>
          </div>
        </div>
      </section>

      {/* Active Auctions */}
      <section className="rule-b">
        <div className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-10 py-16 lg:py-10">
          <div className="flex items-end justify-between mb-8 lg:mb-6">
            <div>
              <div className="overline text-[hsl(var(--accent))]">{t("landing.active")}</div>
              <h2 className="font-serif text-3xl lg:text-5xl tracking-tight mt-3">{t("landing.active_auctions")}</h2>
            </div>
            <Link to="/auctions" className="text-sm hover:text-[hsl(var(--accent))] flex items-center gap-1" data-testid="landing-view-all-auctions">
              {t("cta.view_all")} <ArrowRight size={14} />
            </Link>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6 stagger" data-testid="landing-auctions-grid">
            {auctions.slice(0, 6).map((a) => <AuctionCard key={a.id} auction={a} />)}
          </div>
        </div>
      </section>

      {/* How it works */}
      <section className="rule-b bg-[hsl(var(--surface))]">
        <div className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-10 py-16 lg:py-24">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-10">
            <div className="lg:col-span-4">
              <div className="overline text-[hsl(var(--accent))]">{t("landing.process")}</div>
              <h2 className="font-serif text-3xl lg:text-5xl tracking-tight mt-3">{t("landing.how_it_works")}</h2>
              <p className="mt-5 text-[hsl(var(--ink-muted))] leading-relaxed">
                {t("landing.how_it_works_desc")}
              </p>
            </div>
            <div className="lg:col-span-8 grid grid-cols-1 md:grid-cols-2 gap-0 border border-[hsl(var(--line))] bg-white">
              {[
                { icon: Shield, t: t("landing.steps.s1_title"), d: t("landing.steps.s1_desc") },
                { icon: FileCheck, t: t("landing.steps.s2_title"), d: t("landing.steps.s2_desc") },
                { icon: Gavel, t: t("landing.steps.s3_title"), d: t("landing.steps.s3_desc") },
                { icon: Sparkles, t: t("landing.steps.s4_title"), d: t("landing.steps.s4_desc") },
              ].map((s, i) => (
                <div key={i} className="p-8 rule-b md:border-r md:border-[hsl(var(--line))] md:[&:nth-child(2n)]:border-r-0 md:[&:nth-last-child(-n+2)]:border-b-0">
                  <s.icon size={22} className="text-[hsl(var(--accent))]" />
                  <h3 className="font-serif text-xl mt-5">{s.t}</h3>
                  <p className="mt-3 text-sm text-[hsl(var(--ink-muted))] leading-relaxed">{s.d}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* Featured editorial */}
      {featured.length > 1 && (
        <section className="rule-b">
          <div className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-10 py-16 lg:py-24">
            <div className="flex items-end justify-between mb-10">
              <div>
                <div className="overline text-[hsl(var(--accent))]">{t("landing.editorial")}</div>
                <h2 className="font-serif text-3xl lg:text-5xl tracking-tight mt-3">{t("landing.selected")}</h2>
              </div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 stagger">
              {featured.slice(0, 6).map((a) => <AuctionCard key={a.id} auction={a} />)}
            </div>
          </div>
        </section>
      )}

      {/* Top sales */}
      {sold.length > 0 && (
        <section className="rule-b bg-[hsl(var(--surface))]">
          <div className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-10 py-16 lg:py-24">
            <div className="flex items-end justify-between mb-10">
              <div>
                <div className="overline text-[hsl(var(--accent))]">{t("landing.archive")}</div>
                <h2 className="font-serif text-3xl lg:text-5xl tracking-tight mt-3">{t("landing.recent_sales")}</h2>
              </div>
              <Link to="/sales" className="text-sm hover:text-[hsl(var(--accent))] flex items-center gap-1">
                {t("landing.all_sales")} <ArrowRight size={14} />
              </Link>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
              {sold.slice(0, 4).map((a) => <AuctionCard key={a.id} auction={a} compact />)}
            </div>
          </div>
        </section>
      )}

      {/* CTA */}
      <section className="bg-[hsl(var(--ink))] text-white">
        <div className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-10 py-20 lg:py-28 grid grid-cols-1 lg:grid-cols-12 gap-10 items-center">
          <div className="lg:col-span-7">
            <div className="overline text-[hsl(var(--accent))]" style={{color: "#6DE0B1"}}>{t("cta.join_community_overline")}</div>
            <h2 className="hero-headline text-4xl lg:text-6xl mt-5">{t("cta.ready_next_deal")}</h2>
            <p className="mt-6 text-white/70 max-w-xl leading-relaxed">
              {t("cta.cta_subtitle")}
            </p>
          </div>
          <div className="lg:col-span-5 lg:justify-self-end flex flex-wrap gap-3">
            <Link to="/register" className="btn !border-white bg-white !text-[hsl(var(--ink))] hover:!bg-[hsl(var(--accent))] hover:!text-white hover:!border-[hsl(var(--accent))]" data-testid="cta-register">
              {t("cta.register_free")}
            </Link>
            <Link to="/sell" className="btn !border-white/60 bg-transparent !text-white hover:!bg-white hover:!text-[hsl(var(--ink))]" data-testid="cta-sell">
              {t("cta.sell_car")}
            </Link>
          </div>
        </div>
      </section>
    </main>
  );
}
