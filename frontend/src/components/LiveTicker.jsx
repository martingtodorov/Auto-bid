import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Activity } from "lucide-react";
import { api, formatEUR } from "../lib/apiClient";

export default function LiveTicker() {
  const [items, setItems] = useState([]);

  useEffect(() => {
    const load = async () => {
      try {
        const { data } = await api.get("/auctions", { params: { sort: "most_bids", status: "live", limit: 12 } });
        setItems(data);
      } catch (e) {}
    };
    load();
    const i = setInterval(load, 30000);
    return () => clearInterval(i);
  }, []);

  if (!items.length) return null;
  const loop = [...items, ...items];

  return (
    <div className="bg-[hsl(var(--ink))] text-white overflow-hidden border-b border-black" data-testid="live-ticker">
      <div className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-10 h-9 flex items-center gap-4">
        <div className="shrink-0 flex items-center gap-2 text-xs uppercase tracking-[0.18em] font-semibold">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[hsl(var(--accent))] opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-[hsl(var(--accent))]"></span>
          </span>
          <Activity size={13} /> На живо
        </div>
        <div className="flex-1 overflow-hidden relative">
          <div className="flex gap-10 whitespace-nowrap animate-marquee">
            {loop.map((a, i) => (
              <Link key={i} to={`/auctions/${a.id}`} className="flex items-center gap-3 text-xs font-mono text-white/80 hover:text-white transition">
                <span className="text-white/50">{a.make}</span>
                <span className="truncate max-w-[220px]">{a.title}</span>
                <span className="text-[hsl(var(--accent))] font-semibold" style={{ color: "#6DE0B1" }}>{formatEUR(a.current_bid_eur)}</span>
                <span className="text-white/30">·</span>
                <span className="text-white/40">{a.bid_count} наддав.</span>
                <span className="text-white/20">|</span>
              </Link>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
