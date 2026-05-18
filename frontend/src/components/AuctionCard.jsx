import React, { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { MapPin, Gauge, Fuel, Calendar, Check, Zap, Star, ArrowRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import { formatEUR, formatLocal, formatKM, timeLeft, formatTimeLeft } from "../lib/apiClient";
import { translateEnum } from "../lib/carTranslations";
import { auctionUrl } from "../lib/auctionUrl";
import Picture from "./Picture";

/**
 * AuctionCard with mobile-first horizontal swipe gallery.
 *
 * UX rules (matching Cars&Bids / BringATrailer):
 *   1. First 4 photos are swipable directly inside the card.
 *   2. Slide 5 is NOT another photo — it's a "View Full Auction →" CTA
 *      that funnels the user into the detail page once they've teased
 *      enough of the gallery.
 *   3. Vertical page scroll is preserved — `touch-action: pan-x` on
 *      the scroll container scopes horizontal pans to the carousel
 *      while letting the rest of the page scroll vertically normally.
 *   4. The outer <Link> still works for taps; the browser disambiguates
 *      between "tap" (→ navigate) and "swipe" (→ scroll-snap moves) so
 *      we don't need to install an onClick guard.
 *
 * Performance:
 *   • Uses <Picture> with the backend variant manifest (AVIF → WebP → JPG)
 *     when available; falls back to the legacy single-URL <img> path.
 *   • First card on the page is rendered with `priority` (eager + high
 *     fetchpriority) so Lighthouse can pick it as the LCP candidate.
 *   • Subsequent slides lazy-load.
 */
export default function AuctionCard({ auction, compact = false, priority = false }) {
  const { t, i18n } = useTranslation();
  const [tl, setTl] = useState(() => timeLeft(auction.ends_at));
  const [activeSlide, setActiveSlide] = useState(0);
  const scrollerRef = useRef(null);
  // Track whether the most recent pointer interaction was a horizontal
  // swipe (vs a tap). On mobile the inner scroll-snap container handles
  // the pan, but when the user lifts their finger the browser fires a
  // `click` that bubbles up to the outer <Link> — which would navigate
  // to the detail page mid-swipe, killing the carousel UX. We watch the
  // touch deltas and call `preventDefault()` on that synthetic click
  // when movement exceeded the tap threshold.
  const touchStartRef = useRef(null);
  const isSwipingRef = useRef(false);

  useEffect(() => {
    if (auction.status === "sold" || auction.status === "ended") return;
    const i = setInterval(() => setTl(timeLeft(auction.ends_at)), 1000);
    return () => clearInterval(i);
  }, [auction.ends_at, auction.status]);

  // ---- slide deck: ordered preview (main → exterior → interior × 2) + CTA ----
  // The user-facing rule: keep the visual story consistent — first frame
  // is the cover, second is an exterior beauty, slots 3-4 give a peek
  // into the cabin. The CTA always sits at index 5 (4 photos + CTA).
  //
  // Picker rules:
  //   1. Always show the auction's "main" image first (cover).
  //   2. Then best exterior shot (skipping the one we already picked).
  //   3-4. Then two interior shots if available.
  //   • If a category is missing, fall back to any remaining unused
  //     image preserving original order.
  //
  // Backwards-compat: legacy auctions without category-tagged variants
  // fall through to a simple "first 4 by upload order" picker — which
  // is also what mobile.bg imports give us until we re-tag.
  const variants = auction.images_variants || [];
  const legacyImages = (auction.images && auction.images.length > 0)
    ? auction.images
    : (auction.thumbnails || []);
  const orderedPhotos = pickOrderedPreviewSlides(variants, legacyImages);
  const photoCount = orderedPhotos.length;
  const slides = orderedPhotos.map((entry, i) => ({ kind: "photo", ...entry, slot: i }));
  if (photoCount >= 2) slides.push({ kind: "cta" });

  // Deferred-load gate: the first slide loads instantly (LCP), the rest
  // wait for user intent — touchstart (mobile) or hover (desktop) on
  // the card. This shaves significant bytes off the initial page weight
  // when the visitor is just scrolling past, while keeping the swipe
  // gallery snappy once they show interest.
  const [primed, setPrimed] = useState(false);
  const primeOnce = () => { if (!primed) setPrimed(true); };

  // Track which slide is currently centred — needed for the pagination
  // pills underneath the carousel. IntersectionObserver is the cheapest
  // way: no per-frame `scroll` handler.
  useEffect(() => {
    const root = scrollerRef.current;
    if (!root || slides.length <= 1) return;
    const observer = new IntersectionObserver(
      (entries) => {
        // Pick the entry with the largest intersectionRatio.
        let best = null;
        entries.forEach((e) => {
          if (!best || e.intersectionRatio > best.intersectionRatio) best = e;
        });
        if (best && best.isIntersecting) {
          const idx = Number(best.target.getAttribute("data-slide-index"));
          if (Number.isFinite(idx)) setActiveSlide(idx);
        }
      },
      { root, threshold: [0.55] },
    );
    const children = root.querySelectorAll("[data-slide-index]");
    children.forEach((c) => observer.observe(c));
    return () => observer.disconnect();
  }, [slides.length]);

  const isSold = auction.status === "sold";
  const isEnded = auction.status === "ended";
  const lang = i18n.language;

  return (
    <Link
      to={auctionUrl(auction)}
      className="card-editorial block group"
      data-testid={`auction-card-${auction.id}`}
      onClickCapture={(e) => {
        // Suppress the synthetic click that follows a horizontal swipe
        // — otherwise the outer <Link> hijacks the gesture and the user
        // never sees slide 2+.
        if (isSwipingRef.current) {
          e.preventDefault();
          e.stopPropagation();
          isSwipingRef.current = false;
        }
      }}
    >
      <div
        className="card-img aspect-[3/2] bg-[hsl(var(--surface))] relative overflow-hidden"
        onMouseEnter={primeOnce}
        onTouchStart={primeOnce}
        onPointerDown={primeOnce}
      >
        {slides.length > 1 ? (
          <>
            <div
              ref={scrollerRef}
              className="absolute inset-0 flex overflow-x-auto snap-x snap-mandatory no-scrollbar"
              style={{
                // Allow both axes so a deliberate vertical drag still
                // scrolls the page when the user happens to start their
                // gesture on top of an auction card. The browser
                // disambiguates: a clearly-horizontal pan drives the
                // scroll-snap carousel, a clearly-vertical one bubbles
                // up to the document. Previously we used `pan-x` which
                // *locked* the touch to horizontal panning and silently
                // killed page scroll the moment the user's finger
                // landed on a card image.
                touchAction: "pan-x pan-y",
                scrollbarWidth: "none",
              }}
              onTouchStart={(e) => {
                const t = e.touches[0];
                touchStartRef.current = { x: t.clientX, y: t.clientY, t: Date.now() };
                isSwipingRef.current = false;
              }}
              onTouchMove={(e) => {
                const start = touchStartRef.current;
                if (!start) return;
                const t = e.touches[0];
                // Threshold of 6px feels like the sweet spot — under
                // 6px is firmly a tap, over 6px is a deliberate pan.
                if (Math.abs(t.clientX - start.x) > 6) isSwipingRef.current = true;
              }}
              data-testid={`auction-card-swiper-${auction.id}`}
            >
              {slides.map((s, idx) => (
                <div
                  key={idx}
                  data-slide-index={idx}
                  className="shrink-0 w-full h-full snap-start snap-always relative"
                >
                  {s.kind === "photo" ? (
                    // First slide is the LCP candidate — render eagerly
                    // with the variant manifest. Slides 2-N are deferred
                    // until the user shows intent (touchstart / hover)
                    // via the `primed` flag — keeps initial weight low.
                    (idx === 0 || primed) ? (
                      <Picture
                        variant={s.variant}
                        fallbackSrc={s.fallbackSrc}
                        size="card"
                        alt={`${auction.title} — ${idx + 1}`}
                        className="absolute inset-0 w-full h-full object-cover"
                        priority={priority && idx === 0}
                        draggable={false}
                      />
                    ) : (
                      <div
                        className="absolute inset-0 bg-[hsl(var(--surface))]"
                        aria-hidden="true"
                        data-testid={`auction-card-slide-placeholder-${idx}`}
                      />
                    )
                  ) : (
                    <CtaSlide title={t("auction.view_full_auction", "Виж пълния търг")} />
                  )}
                </div>
              ))}
            </div>
            {/* Pagination pills — tap-targets are 8x8 px squares with
                generous touch padding via the parent's height. */}
            <div className="absolute bottom-3 left-1/2 -translate-x-1/2 z-10 flex items-center gap-1.5 px-2 py-1 rounded-full bg-black/40 backdrop-blur-sm pointer-events-none">
              {slides.map((s, idx) => (
                <span
                  key={idx}
                  className={`block w-1.5 h-1.5 rounded-full transition-all ${
                    idx === activeSlide
                      ? (s.kind === "cta"
                          ? "bg-[hsl(var(--accent))] w-3"
                          // Use an arbitrary `#ffffff` value (not the
                          // `bg-white` class) so the dark-theme
                          // `.bg-white` remap defined in index.css
                          // can't catch it — pagination dots must stay
                          // crisp-white on both themes.
                          : "bg-[#ffffff] w-3")
                      : "bg-white/50"
                  }`}
                  aria-hidden="true"
                />
              ))}
            </div>
          </>
        ) : (
          // Single-image legacy fallback — no carousel chrome, no JS.
          <Picture
            variant={slides[0]?.variant}
            fallbackSrc={slides[0]?.fallbackSrc || legacyImages[0]}
            size="card"
            alt={auction.title}
            className="absolute inset-0 w-full h-full object-cover"
            priority={priority}
            draggable={false}
          />
        )}
        <div className="absolute top-3 left-3 flex gap-2 flex-wrap max-w-[calc(100%-1.5rem)] z-10 pointer-events-none">
          {isSold ? (
            <span className="pill pill-sold">{t("my_listings.status.sold")}</span>
          ) : isEnded ? (
            <span className="pill pill-sold">{t("my_listings.status.ended")}</span>
          ) : tl.urgent ? (
            <span className="pill pill-ending">{formatTimeLeft(tl, t)}</span>
          ) : (
            <span className="pill pill-live">{formatTimeLeft(tl, t)}</span>
          )}
          {auction.featured && !isSold && (
            <span
              className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-[hsl(var(--accent))] text-white shadow-sm"
              data-testid={`featured-badge-${auction.id}`}
              title={t("auction.featured_badge")}
              aria-label={t("auction.featured_badge")}
            >
              <Star size={12} fill="currentColor" strokeWidth={0} />
            </span>
          )}
          {auction.vat_status === "vat_inclusive" && !["sold", "ended"].includes(auction.status) && (
            <span
              className="pill pill-vat"
              data-testid={`vat-badge-${auction.id}`}
              title={`VAT ${auction.vat_rate_pct || 20}%`}
            >
              {t("auction.vat_short", "ДДС")}
            </span>
          )}
          {auction.seller_is_verified_dealer && !["sold", "ended"].includes(auction.status) && (
            <span className="pill pill-verified flex items-center gap-1" data-testid={`verified-dealer-${auction.id}`}>
              <Check size={11} strokeWidth={3} /> {t("auction.dealer_badge")}
            </span>
          )}
        </div>
      </div>

      <div className="p-5">
        <h3 className="font-serif text-xl leading-tight tracking-tight group-hover:text-[hsl(var(--accent))] transition-colors">
          {auction.title}
        </h3>

        {!compact && (
          <div className="mt-3 grid grid-cols-2 gap-y-1.5 gap-x-4 text-[13px] text-[hsl(var(--ink-muted))]">
            <span className="flex items-center gap-1.5 min-w-0"><Calendar size={13} className="shrink-0" />{auction.year}</span>
            <span className="flex items-center gap-1.5 min-w-0"><Gauge size={13} className="shrink-0" />{formatKM(auction.mileage_km)}</span>
            <span className="flex items-center gap-1.5 min-w-0"><Fuel size={13} className="shrink-0" />{translateEnum(auction.fuel, "fuel", lang)}</span>
            <span className="flex items-center gap-1.5 min-w-0"><MapPin size={13} className="shrink-0" /><span className="truncate">{translateEnum(auction.city, "city", lang)}{auction.country ? `, ${auction.country}` : ""}</span></span>
          </div>
        )}

        <div className="mt-4 rule-t pt-4 flex items-start justify-between gap-3">
          {/* Price block — left aligned (current bid / sold price + buy-now pill) */}
          <div className="min-w-0">
            <div className="overline text-[hsl(var(--ink-muted))]">
              {isSold ? t("auction.sold_for") : t("auction.current_bid_label")}
            </div>
            <div className="font-serif text-2xl mt-1 flex items-baseline gap-1.5 flex-wrap" data-testid={`auction-price-${auction.id}`}>
              {auction.vat_status === "vat_inclusive" && Number(auction.vat_rate_pct) > 0
                ? formatEUR(Math.round(Number(auction.current_bid_eur || 0) * (1 + Number(auction.vat_rate_pct) / 100)))
                : formatEUR(auction.current_bid_eur)}
              {auction.vat_status === "vat_inclusive" && (
                <span className="text-[10px] uppercase tracking-wider text-[hsl(var(--ink-muted))] font-sans font-semibold">
                  {t("auction.incl_vat", "вкл. ДДС")}
                </span>
              )}
            </div>
            <div className="text-xs text-[hsl(var(--ink-muted))] font-mono">
              {auction.vat_status === "vat_inclusive" && Number(auction.vat_rate_pct) > 0
                ? formatLocal(Math.round(Number(auction.current_bid_eur || 0) * (1 + Number(auction.vat_rate_pct) / 100)), lang)
                : formatLocal(auction.current_bid_eur, lang)}
            </div>
            {!isSold && auction.buy_now_eur && Number(auction.buy_now_eur) > Number(auction.current_bid_eur || 0) && (
              <div
                className="mt-2 inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md bg-[hsl(var(--accent-soft))] border border-[hsl(var(--accent))]/30 text-[11px] font-semibold text-[hsl(var(--accent-ink))]"
                data-testid={`buy-now-${auction.id}`}
                title={t("auction.buy_now_title", "Купи сега")}
              >
                <Zap size={11} />
                <span>{t("auction.buy_now_short", "Купи сега")}: {formatEUR(
                  auction.vat_status === "vat_inclusive" && Number(auction.vat_rate_pct) > 0
                    ? Math.round(Number(auction.buy_now_eur) * (1 + Number(auction.vat_rate_pct) / 100))
                    : auction.buy_now_eur
                )}</span>
              </div>
            )}
          </div>

          {/* Reserve badge — right aligned, vertically centred against the price */}
          {!isSold && (
            <div className="shrink-0 self-center">
              {auction.has_reserve ? (
                <span className="inline-flex items-center gap-1.5 text-[13px] font-semibold text-[hsl(var(--ink))] bg-[hsl(var(--surface))] px-3 py-1.5 rounded-full border border-[hsl(var(--line))]" data-testid={`with-reserve-${auction.id}`}>
                  ● {t("auction.with_reserve")}
                </span>
              ) : (
                <span className="no-reserve-gradient inline-flex items-center gap-1.5 text-[13px] font-semibold px-3 py-1.5 rounded-full" data-testid={`no-reserve-${auction.id}`}>
                  ● {t("auction.no_reserve_badge")}
                </span>
              )}
            </div>
          )}
        </div>
      </div>
    </Link>
  );
}

/**
 * Pick up to 4 preview slides in the order: main → exterior → interior
 * → interior, falling back to any remaining unused image when a category
 * is missing.
 *
 * Each returned entry has shape `{ variant, fallbackSrc, sourceIndex }`
 * — sourceIndex points back into the original arrays so React keys
 * stay stable across re-renders.
 */
function pickOrderedPreviewSlides(variants, legacyImages) {
  const used = new Set();
  const out = [];
  // Helper to push an index into the result if it's unused.
  const push = (idx) => {
    if (idx == null || idx < 0) return false;
    if (used.has(idx)) return false;
    used.add(idx);
    out.push({
      variant: variants[idx] || null,
      fallbackSrc: legacyImages[idx] || (variants[idx] && variants[idx].primary) || null,
      sourceIndex: idx,
    });
    return true;
  };
  // Index by category to skim categorized variants in one pass.
  const byCategory = (() => {
    const map = { main: [], exterior: [], interior: [], detail: [], damage: [], documents: [], other: [] };
    variants.forEach((v, i) => {
      const cat = (v && v.category) || "other";
      if (map[cat]) map[cat].push(i); else map.other.push(i);
    });
    return map;
  })();
  // 1. main (cover). If absent, fall through to first exterior.
  if (!push((byCategory.main || [])[0])) push((byCategory.exterior || [])[0]);
  // 2. exterior — best one that wasn't already picked above.
  push((byCategory.exterior || []).find((i) => !used.has(i)));
  // 3-4. up to two interior shots.
  (byCategory.interior || []).slice(0, 2).forEach(push);
  // Fill any remaining slots with whatever else exists, preserving the
  // original upload order so e.g. a "detail" or "damage" tagged image
  // still shows when there are no interior shots.
  const total = Math.max(variants.length, legacyImages.length);
  for (let i = 0; i < total && out.length < 4; i += 1) push(i);
  return out;
}


/** "View full auction" terminal slide — last panel in the swipe deck.
 *  Visually distinctive (subtle gradient + arrow) so users get a clear
 *  end-of-deck signal and a strong "open the listing" CTA. */
function CtaSlide({ title }) {
  return (
    <div
      className="absolute inset-0 flex flex-col items-center justify-center bg-gradient-to-br from-[hsl(var(--bg))] to-[hsl(var(--surface))] text-center px-6"
      data-testid="auction-card-cta-slide"
    >
      <ArrowRight size={32} className="text-[hsl(var(--accent))] mb-2" />
      <div className="font-serif text-lg">{title}</div>
      <div className="mt-1 text-[11px] uppercase tracking-wider text-[hsl(var(--ink-muted))]">
        Tap to open
      </div>
    </div>
  );
}
