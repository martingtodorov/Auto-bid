import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { MapPin, Gauge, Fuel, Calendar, Users, Shield, Zap, Star } from "lucide-react";
import { useTranslation } from "react-i18next";
import { formatEUR, formatLocal, formatKM, timeLeft, formatTimeLeft } from "../lib/apiClient";
import { translateEnum } from "../lib/carTranslations";
import { auctionUrl } from "../lib/auctionUrl";

export default function AuctionCard({ auction, compact = false, priority = false }) {
  const { t, i18n } = useTranslation();
  const [tl, setTl] = useState(() => timeLeft(auction.ends_at));

  useEffect(() => {
    if (auction.status === "sold" || auction.status === "ended") return;
    const i = setInterval(() => setTl(timeLeft(auction.ends_at)), 1000);
    return () => clearInterval(i);
  }, [auction.ends_at, auction.status]);

  const isSold = auction.status === "sold";
  const isEnded = auction.status === "ended";
  const lang = i18n.language;

  return (
    <Link
      to={auctionUrl(auction)}
      className="card-editorial block group"
      data-testid={`auction-card-${auction.id}`}
    >
      <div className="card-img aspect-[4/3] bg-[hsl(var(--surface))]">
        <img
          src={auction.thumbnails?.[0] || auction.images?.[0]}
          srcSet={
            auction.thumbnails?.[0] && auction.images?.[0]
              ? `${auction.thumbnails[0]} 400w, ${auction.images[0]} 1600w`
              : undefined
          }
          sizes="(min-width: 1024px) 380px, (min-width: 640px) 50vw, 100vw"
          alt={auction.title}
          // Top-of-page cards get eager + high priority so Lighthouse can
          // discover the LCP candidate without waiting on the JS bundle.
          loading={priority ? "eager" : "lazy"}
          fetchpriority={priority ? "high" : "auto"}
          decoding="async"
        />
        <div className="absolute top-3 left-3 flex gap-2 flex-wrap max-w-[calc(100%-1.5rem)]">
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
          {auction.vat_status === "vat_inclusive" && (
            <span
              className="pill pill-vat"
              data-testid={`vat-badge-${auction.id}`}
              title={`VAT ${auction.vat_rate_pct || 20}%`}
            >
              {t("auction.vat_short", "ДДС")}
            </span>
          )}
          {auction.seller_is_verified_dealer && (
            <span className="pill pill-verified flex items-center gap-1" data-testid={`verified-dealer-${auction.id}`}>
              <Shield size={10} /> {t("auction.verified_dealer")}
            </span>
          )}
        </div>
      </div>

      <div className="p-5">
        <div className="flex items-baseline justify-between gap-3">
          <h3 className="font-serif text-xl leading-tight tracking-tight group-hover:text-[hsl(var(--accent))] transition-colors">
            {auction.title}
          </h3>
        </div>

        {!compact && (
          <div className="mt-3 grid grid-cols-2 gap-y-1.5 gap-x-4 text-[13px] text-[hsl(var(--ink-muted))]">
            <span className="flex items-center gap-1.5"><Calendar size={13} />{auction.year}</span>
            <span className="flex items-center gap-1.5"><Gauge size={13} />{formatKM(auction.mileage_km)}</span>
            <span className="flex items-center gap-1.5"><Fuel size={13} />{translateEnum(auction.fuel, "fuel", lang)}</span>
            <span className="flex items-center gap-1.5"><MapPin size={13} />{translateEnum(auction.city, "city", lang)}{auction.country ? `, ${auction.country}` : ""}</span>
          </div>
        )}

        <div className="mt-4 rule-t pt-4 flex items-start justify-between gap-3">
          <div>
            <div className="overline text-[hsl(var(--ink-muted))]">
              {isSold ? t("auction.sold_for") : t("auction.current_bid_label")}
            </div>
            <div className="font-serif text-2xl mt-1 flex items-baseline gap-1.5" data-testid={`auction-price-${auction.id}`}>
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
          <div className="text-right">
            <div className="overline text-[hsl(var(--ink-muted))]">{t("auction.bids_history_title")}</div>
            <div className="flex items-center gap-1.5 mt-1 text-sm font-mono justify-end"><Users size={13} />{auction.bid_count || 0}</div>
            {!isSold && (
              <div className="mt-2.5">
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
      </div>
    </Link>
  );
}
