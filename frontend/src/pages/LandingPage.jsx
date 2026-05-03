import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowRight, Shield, Gavel, FileCheck, Sparkles } from "lucide-react";
import DOMPurify from "dompurify";
import { api, formatEUR, formatLocal } from "../lib/apiClient";
import { readLandingCache, landingCacheIsFresh, fetchLandingData } from "../lib/landingCache";
import AuctionCard from "../components/AuctionCard";
import { setPageMeta, resetPageMeta } from "../lib/seo";
import { useSiteSettings } from "../lib/settings";
import { translateEnum } from "../lib/carTranslations";
import { auctionUrl } from "../lib/auctionUrl";

const HERO_IMAGE = "https://images.unsplash.com/photo-1698995339730-86b3dd454001?crop=entropy&cs=srgb&fm=jpg&q=85&w=2000";

export default function LandingPage() {
  const { t, i18n } = useTranslation();
  // Seed from sessionStorage so navigating back to `/` shows the last-known
  // homepage instantly while the background refresh catches up. `null`-safe —
  // first-ever visit falls through to empty arrays.
  const cached = typeof window !== "undefined" ? readLandingCache() : null;
  const [auctions, setAuctions] = useState(cached?.live || []);
  const [featured, setFeatured] = useState(cached?.featured || []);
  const [sold, setSold] = useState(cached?.sold || []);
  const [heroPicks, setHeroPicks] = useState(cached?.hero || []);
  const settings = useSiteSettings();

  // Update SEO from site settings (per-language, fallback to legacy field)
  const lang = (i18n.resolvedLanguage || "bg").slice(0, 2);
  const seoTitle = settings?.[`seo_title_${lang}`] || settings?.seo_title;
  const seoDescription = settings?.[`seo_description_${lang}`] || settings?.seo_description;
  useEffect(() => {
    if (seoTitle || seoDescription) {
      setPageMeta({
        title: seoTitle,
        description: seoDescription,
        url: window.location.origin,
      });
    }
    return () => resetPageMeta();
  }, [seoTitle, seoDescription]);

  useEffect(() => {
    let cancelled = false;

    const applyPayload = (payload) => {
      if (cancelled || !payload) return;
      setAuctions(payload.live || []);
      setFeatured(payload.featured || []);
      setSold(payload.sold || []);
      setHeroPicks(payload.hero || []);
    };

    const refresh = async () => {
      try {
        const payload = await fetchLandingData();
        applyPayload(payload);
      } catch (e) {
        // Keep whatever we're already showing (cache or prior fetch).
        console.error(e);
      }
    };

    // First paint: render cache immediately if still fresh, otherwise fetch.
    const seed = readLandingCache();
    if (landingCacheIsFresh(seed)) {
      applyPayload(seed);
    } else {
      refresh();
    }

    // Background refresh every 60s so auctions that end / get pulled drop
    // off the homepage without requiring a full reload.
    const intervalId = setInterval(refresh, 60 * 1000);

    // Extra refresh when the tab regains focus after being backgrounded —
    // Chrome pauses setInterval on hidden tabs.
    const onVisible = () => {
      if (document.visibilityState === "visible") refresh();
    };
    document.addEventListener("visibilitychange", onVisible);

    return () => {
      cancelled = true;
      clearInterval(intervalId);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, []);

  // Two heroes now — backend /auctions/hero returns up to 2 picks with
  // 30-min stickiness (featured flag + bid/comment activity). Fall back to
  // featured[0..1] / auctions[0..1] if the endpoint is unavailable.
  const heroes = heroPicks.length
    ? heroPicks.slice(0, 2)
    : (featured.slice(0, 2).length >= 2
        ? featured.slice(0, 2)
        : [featured[0], auctions[0]].filter(Boolean).slice(0, 2));
  const heroIds = new Set(heroes.map((h) => h.id));
  // Filter the lists below so hero cars never render twice on the page.
  // (Previously we also built `featuredEx` for the "Selected listings"
  // section — removed per product decision: promoted auctions now take
  // the lead slots in the Active Auctions grid instead.)
  // Active-auction overview: 9 cards total, promoted ones first. We
  // partition the active list into `featured` (paid promotion) + the
  // rest, dedupe against heroes, then concatenate so promoted cards
  // always win the top slots on the landing page. Heroes are already
  // stripped via `heroIds` above so nothing renders twice.
  const auctionsEx = auctions.filter((a) => !heroIds.has(a.id));
  const featuredIds = new Set(featured.map((f) => f.id));
  const promotedActive = auctionsEx.filter((a) => featuredIds.has(a.id) || a.featured);
  const regularActive = auctionsEx.filter((a) => !featuredIds.has(a.id) && !a.featured);
  const activeOverview = [...promotedActive, ...regularActive].slice(0, 9);

  // CMS-editable hero text per language (falls back to static i18n)
  const cmsHeadline = settings?.[`hero_headline_${lang}`];
  const cmsSubtitle = settings?.[`hero_subtitle_${lang}`];

  return (
    <main data-testid="landing-page">
      {/* Hero */}
      <section className="rule-b hero-ambient">
        <div className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-10 py-6 lg:py-3">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 lg:gap-10 items-center">
            <div className="lg:col-span-5 fade-up">
              {cmsHeadline ? (
                <h1
                  className="hero-headline text-5xl sm:text-6xl lg:text-[60px] lg:leading-[1.05] mt-0"
                  data-testid="hero-headline-cms"
                  dangerouslySetInnerHTML={{
                    __html: DOMPurify.sanitize(cmsHeadline.replace(/\n/g, "<br />"), {
                      ALLOWED_TAGS: ["br", "em", "strong", "span", "b", "i"],
                      ALLOWED_ATTR: ["class"],
                    }),
                  }}
                />
              ) : (
                <h1 className="hero-headline text-5xl sm:text-6xl lg:text-[60px] lg:leading-[1.05] mt-0 text-balance" data-testid="hero-headline-i18n">
                  {t("hero.discover")} <em>{t("hero.exceptional")}</em> {t("hero.cars")}
                </h1>
              )}
              <p className="mt-5 text-base lg:text-lg text-[hsl(var(--ink-muted))] leading-relaxed max-w-xl" data-testid="hero-subtitle">
                {cmsSubtitle || t("hero.subtitle")}
              </p>
              <div className="mt-6 flex flex-nowrap gap-2 sm:gap-3">
                <Link to="/auctions" className="btn btn-primary flex-1 sm:flex-none !px-3 sm:!px-8 !text-sm whitespace-nowrap" data-testid="hero-cta-browse">
                  {t("hero.browse")} <ArrowRight size={14} className="ml-1.5 sm:ml-2" />
                </Link>
                <Link to="/sell" className="btn btn-sell-gradient flex-1 sm:flex-none !px-3 sm:!px-8 !text-sm whitespace-nowrap" data-testid="hero-cta-sell">
                  {t("hero.sell_cta")}
                </Link>
              </div>
            </div>

            <div className="lg:col-span-7 fade-up">
              {heroes.length > 0 ? (
                <div data-testid="hero-featured-auction">
                  <h2 className="overline text-[hsl(var(--accent))] mb-2 font-sans !text-xs !leading-tight !tracking-widest">{t("hero.featured_listing")}</h2>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 lg:gap-5">
                    {heroes.map((h, idx) => (
                      <AuctionCard key={h.id} auction={h} priority={idx === 0} />
                    ))}
                  </div>
                </div>
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
            {activeOverview.map((a) => <AuctionCard key={a.id} auction={a} />)}
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

      {/* Featured/Selected listings removed — promoted auctions now appear
          first in the Active Auctions grid above. */}

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

      {/* CTA — intentionally always dark to provide contrast with the rest of the page. */}
      <section className="bg-black text-white">
        <div className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-10 py-20 lg:py-28 grid grid-cols-1 lg:grid-cols-12 gap-10 items-center">
          <div className="lg:col-span-7">
            <div className="overline" style={{color: "#6DE0B1"}}>{t("cta.join_community_overline")}</div>
            <h2 className="hero-headline text-4xl lg:text-6xl mt-5">{t("cta.ready_next_deal")}</h2>
            <p className="mt-6 text-white/70 max-w-xl leading-relaxed">
              {t("cta.cta_subtitle")}
            </p>
          </div>
          <div className="lg:col-span-5 lg:justify-self-end flex flex-wrap gap-3">
            <Link to="/register" className="btn !border-white !bg-[#fff] !text-[#0a0a0a] hover:!bg-[hsl(var(--accent))] hover:!text-[#0a0a0a] hover:!border-[hsl(var(--accent))]" data-testid="cta-register">
              {t("cta.register_free")}
            </Link>
            <Link to="/sell" className="btn !border-white/60 bg-transparent !text-white hover:!bg-[#fff] hover:!text-[#0a0a0a]" data-testid="cta-sell">
              {t("cta.sell_car")}
            </Link>
          </div>
        </div>
      </section>
    </main>
  );
}
