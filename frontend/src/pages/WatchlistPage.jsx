import React, { useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { Heart } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../lib/auth";
import { api } from "../lib/apiClient";
import AuctionCard from "../components/AuctionCard";
import { usePrivatePageMeta } from "../lib/usePrivatePageMeta";
import { useBrandName } from "../lib/brand";

export default function WatchlistPage() {
  const { t } = useTranslation();
  const brand = useBrandName();
  const { user, loading } = useAuth();
  const [items, setItems] = useState(null);
  usePrivatePageMeta({ titleKey: "page_meta.watchlist_title", descKey: "page_meta.watchlist_desc", brand });

  useEffect(() => {
    if (!user) return;
    api.get("/me/watchlist").then((r) => setItems(r.data)).catch(() => setItems([]));
  }, [user]);

  if (loading) return <div className="py-24 text-center">{t("watchlist.loading")}</div>;
  if (!user) return <Navigate to="/login?next=/watchlist" replace />;

  return (
    <main data-testid="watchlist-page">
      <div className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-10 py-16">
        <div className="overline text-[hsl(var(--accent))]">{t("watchlist.overline")}</div>
        <h1 className="font-serif text-4xl lg:text-5xl tracking-tight mt-3">{t("watchlist.title")}</h1>
        <p className="mt-3 text-sm text-[hsl(var(--ink-muted))]">{t("watchlist.subtitle")}</p>

        {items === null ? (
          <div className="py-20 text-center text-[hsl(var(--ink-muted))]">{t("watchlist.loading")}</div>
        ) : items.length === 0 ? (
          <div className="mt-12 py-20 text-center rounded-card border border-[hsl(var(--line))]" data-testid="watchlist-empty">
            <Heart size={32} className="mx-auto text-[hsl(var(--ink-muted))]" />
            <p className="mt-4 font-serif text-2xl">{t("watchlist.empty_title")}</p>
            <p className="mt-2 text-sm text-[hsl(var(--ink-muted))]">{t("watchlist.empty_hint")}</p>
            <Link to="/auctions" className="btn btn-primary mt-6 inline-flex" data-testid="watchlist-browse-cta">{t("watchlist.browse")}</Link>
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
