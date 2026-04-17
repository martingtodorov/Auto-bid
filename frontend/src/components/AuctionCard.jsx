import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { MapPin, Gauge, Fuel, Calendar, Users, Shield } from "lucide-react";
import { formatEUR, formatBGN, formatKM, timeLeft } from "../lib/apiClient";

export default function AuctionCard({ auction, compact = false }) {
  const [t, setT] = useState(() => timeLeft(auction.ends_at));

  useEffect(() => {
    if (auction.status === "sold" || auction.status === "ended") return;
    const i = setInterval(() => setT(timeLeft(auction.ends_at)), 1000);
    return () => clearInterval(i);
  }, [auction.ends_at, auction.status]);

  const isSold = auction.status === "sold";
  const isEnded = auction.status === "ended";

  return (
    <Link
      to={`/auctions/${auction.id}`}
      className="card-editorial block group"
      data-testid={`auction-card-${auction.id}`}
    >
      <div className="card-img aspect-[4/3] bg-[hsl(var(--surface))]">
        <img src={auction.images?.[0]} alt={auction.title} loading="lazy" />
        <div className="absolute top-3 left-3 flex gap-2 flex-wrap max-w-[calc(100%-1.5rem)]">
          {isSold ? (
            <span className="pill pill-sold">Продаден</span>
          ) : isEnded ? (
            <span className="pill pill-sold">Приключил</span>
          ) : t.urgent ? (
            <span className="pill pill-ending">{t.label}</span>
          ) : (
            <span className="pill pill-live">{t.label}</span>
          )}
          {auction.featured && !isSold && <span className="pill">Промотирана</span>}
          {auction.seller_is_verified_dealer && (
            <span className="pill pill-verified flex items-center gap-1" data-testid={`verified-dealer-${auction.id}`}>
              <Shield size={10} /> Проверен дилър
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
            <span className="flex items-center gap-1.5"><Fuel size={13} />{auction.fuel}</span>
            <span className="flex items-center gap-1.5"><MapPin size={13} />{auction.city}</span>
          </div>
        )}

        <div className="mt-4 rule-t pt-4 flex items-start justify-between gap-3">
          <div>
            <div className="overline text-[hsl(var(--ink-muted))]">
              {isSold ? "Продаден за" : "Текуща наддавка"}
            </div>
            <div className="font-serif text-2xl mt-1" data-testid={`auction-price-${auction.id}`}>
              {formatEUR(auction.current_bid_eur)}
            </div>
            <div className="text-xs text-[hsl(var(--ink-muted))] font-mono">{formatBGN(auction.current_bid_eur)}</div>
          </div>
          <div className="text-right">
            <div className="overline text-[hsl(var(--ink-muted))]">Наддавания</div>
            <div className="flex items-center gap-1.5 mt-1 text-sm font-mono justify-end"><Users size={13} />{auction.bid_count || 0}</div>
            {!isSold && (
              <div className="mt-2">
                {auction.has_reserve ? (
                  auction.reserve_met ? (
                    <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-[hsl(var(--accent))] bg-[hsl(var(--accent-soft))] px-2 py-1 rounded-full border border-[hsl(var(--accent))]/30" data-testid={`reserve-met-${auction.id}`}>
                      ● Резервът е достигнат
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-[hsl(var(--ink-muted))] bg-[hsl(var(--surface))] px-2 py-1 rounded-full border border-[hsl(var(--line))]" data-testid={`with-reserve-${auction.id}`}>
                      ● С резерв
                    </span>
                  )
                ) : (
                  <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-[hsl(var(--ink))] bg-white px-2 py-1 rounded-full border border-[hsl(var(--line))]" data-testid={`no-reserve-${auction.id}`}>
                    ● Без резерв
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
