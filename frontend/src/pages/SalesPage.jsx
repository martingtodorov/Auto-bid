import React, { useEffect, useState } from "react";
import { api } from "../lib/apiClient";
import AuctionCard from "../components/AuctionCard";

export default function SalesPage() {
  const [items, setItems] = useState([]);
  useEffect(() => {
    api.get("/auctions/sold").then((r) => setItems(r.data));
  }, []);

  return (
    <main className="rule-b" data-testid="sales-page">
      <div className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-10 py-16">
        <div className="overline text-[hsl(var(--accent))]">Архив</div>
        <h1 className="font-serif text-4xl lg:text-5xl mt-3 tracking-tight">Последни продажби</h1>
        <p className="mt-3 text-sm text-[hsl(var(--ink-muted))] max-w-xl">
          Вижте кои автомобили намериха новите си собственици чрез AutoBid.bg.
        </p>

        <div className="mt-12 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6 stagger">
          {items.map((a) => <AuctionCard key={a.id} auction={a} compact />)}
        </div>
      </div>
    </main>
  );
}
