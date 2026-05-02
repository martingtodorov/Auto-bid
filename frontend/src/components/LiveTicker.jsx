import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api, formatEUR } from "../lib/apiClient";
import { grossEUR } from "../lib/vat";
import { auctionUrl } from "../lib/auctionUrl";

/** Top promoted-listings ticker.
 *  - Fetches every featured/live auction so the loop covers them all.
 *  - Seamless infinite marquee: two identical halves, animation translates
 *    by EXACTLY -50% of the wrapper width. To make -50% land precisely at
 *    the start of the second half, the inter-item gap is baked into each
 *    item's right margin (no flex `gap`) — otherwise a half-gap offset
 *    creates a visible jump on every loop.
 *  - Fully scrollable on touch (overflow-x), animation pauses while the
 *    user is interacting, then resumes from where it was. */
export default function LiveTicker() {
  const { t } = useTranslation();
  const [items, setItems] = useState([]);

  useEffect(() => {
    const load = async () => {
      try {
        const { data } = await api.get("/auctions/featured", { params: { view: "list" } });
        setItems(Array.isArray(data) ? data : []);
      } catch (e) {}
    };
    load();
    const i = setInterval(load, 30000);
    return () => clearInterval(i);
  }, []);

  if (!items.length) return null;
  const loop = [...items, ...items];

  return (
    <div className="bg-black text-white border-b border-[hsl(var(--line))]" data-testid="live-ticker">
      <div className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-10 h-9 flex items-center">
        <div className="flex-1 overflow-hidden relative ticker-scroll">
          <div className="flex whitespace-nowrap animate-marquee w-max">
            {loop.map((a, i) => (
              <Link
                key={i}
                to={auctionUrl(a)}
                className="flex items-center gap-3 text-xs font-mono text-white/80 hover:text-white transition shrink-0 pr-10"
                data-testid={`ticker-item-${i}`}
              >
                <span className="truncate max-w-[220px]">{a.title}</span>
                <span className="font-semibold" style={{ color: "#6DE0B1" }}>{formatEUR(grossEUR(a.current_bid_eur, a))}</span>
                <span className="text-white/30">·</span>
                <span className="text-white/40">{a.bid_count || 0} {t("time.bids_short")}</span>
                <span className="text-white/20 ml-3">|</span>
              </Link>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
