import React, { useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { Heart } from "lucide-react";
import { useAuth } from "../lib/auth";
import { api } from "../lib/apiClient";
import AuctionCard from "../components/AuctionCard";

export default function WatchlistPage() {
  const { user, loading } = useAuth();
  const [items, setItems] = useState(null);

  useEffect(() => {
    if (!user) return;
    api.get("/me/watchlist").then((r) => setItems(r.data)).catch(() => setItems([]));
  }, [user]);

  if (loading) return <div className="py-24 text-center">Зареждане…</div>;
  if (!user) return <Navigate to="/login?next=/watchlist" replace />;

  return (
    <main data-testid="watchlist-page">
      <div className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-10 py-16">
        <div className="overline text-[hsl(var(--accent))]">Моят списък</div>
        <h1 className="font-serif text-4xl lg:text-5xl tracking-tight mt-3">Любими търгове</h1>
        <p className="mt-3 text-sm text-[hsl(var(--ink-muted))]">Всички автомобили, които сте маркирали като любими.</p>

        {items === null ? (
          <div className="py-20 text-center text-[hsl(var(--ink-muted))]">Зареждане…</div>
        ) : items.length === 0 ? (
          <div className="mt-12 py-20 text-center rounded-card border border-[hsl(var(--line))]">
            <Heart size={32} className="mx-auto text-[hsl(var(--ink-muted))]" />
            <p className="mt-4 font-serif text-2xl">Списъкът е празен</p>
            <p className="mt-2 text-sm text-[hsl(var(--ink-muted))]">Натиснете "Добави в любими" в детайлите на обявите.</p>
            <Link to="/auctions" className="btn btn-primary mt-6 inline-flex">Разгледай търгове</Link>
          </div>
        ) : (
          <div className="mt-12 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6 stagger" data-testid="watchlist-grid">
            {items.map((a) => <AuctionCard key={a.id} auction={a} />)}
          </div>
        )}
      </div>
    </main>
  );
}
