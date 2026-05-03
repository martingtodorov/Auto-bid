import { useEffect, useState } from "react";
import { useParams, Link, Navigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { BadgeCheck, MapPin, Star } from "lucide-react";

import { api } from "../lib/apiClient";
import AuctionCard from "../components/AuctionCard";

// Reserved top-level paths must NOT resolve against /api/dealers — they
// are real pages owned by the SPA. If a visitor types /login we want
// LoginPage, not a 404 from the dealer lookup. Keep this list in sync
// with App.js.
const RESERVED_SLUGS = new Set([
  "", "auctions", "how-it-works", "sales", "sell", "login", "register",
  "forgot-password", "dashboard", "admin", "watchlist", "my-listings",
  "inbox", "profile", "settings", "faq", "fees", "contacts", "terms",
  "verify-email", "api", "uploads", "og", "static", "assets",
]);

export default function DealerPage() {
  const { dealerSlug: raw } = useParams();
  const { t } = useTranslation();
  const [state, setState] = useState({ loading: true, data: null, notFound: false });

  const slug = (raw || "").trim();

  useEffect(() => {
    if (!slug || RESERVED_SLUGS.has(slug.toLowerCase())) {
      // Never hit the API for reserved paths — the SPA router should have
      // dispatched them already; this branch exists as a seatbelt.
      setState({ loading: false, data: null, notFound: true });
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const { data } = await api.get(`/dealers/${encodeURIComponent(slug)}`);
        if (!cancelled) setState({ loading: false, data, notFound: false });
      } catch {
        if (!cancelled) setState({ loading: false, data: null, notFound: true });
      }
    })();
    return () => { cancelled = true; };
  }, [slug]);

  if (!slug) return <Navigate to="/" replace />;
  if (state.loading) {
    return (
      <div className="max-w-6xl mx-auto px-4 py-16 text-center text-[hsl(var(--ink-muted))]">
        {t("common.loading", "Зареждам…")}
      </div>
    );
  }
  if (state.notFound || !state.data) {
    return (
      <div className="max-w-6xl mx-auto px-4 py-20 text-center">
        <div className="font-serif text-5xl mb-4">404</div>
        <p className="text-[hsl(var(--ink-muted))] mb-8">
          {t("dealer.not_found", "Няма дилър с това име.")}
        </p>
        <Link to="/" className="btn btn-primary inline-flex" data-testid="dealer-404-home">
          {t("dealer.back_home", "Към началната страница")}
        </Link>
      </div>
    );
  }

  const { dealer, rating, active_listings, recently_sold, counts } = state.data;

  return (
    <div className="max-w-6xl mx-auto px-4 py-10">
      {/* Header */}
      <div className="flex flex-col md:flex-row items-start md:items-center gap-5 pb-8 border-b border-[hsl(var(--line))]">
        <div className="w-20 h-20 rounded-full bg-[hsl(var(--surface))] border border-[hsl(var(--line))] overflow-hidden flex items-center justify-center shrink-0">
          {dealer.avatar_url
            ? <img src={dealer.avatar_url} alt={dealer.name} className="w-full h-full object-cover" />
            : <span className="font-serif text-3xl text-[hsl(var(--ink-muted))]">{dealer.name?.[0] || "?"}</span>}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h1 className="font-serif text-4xl" data-testid="dealer-name">{dealer.name}</h1>
            <span
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-[hsl(var(--accent))]/15 text-[hsl(var(--accent))]"
              data-testid="dealer-verified-badge"
            >
              <BadgeCheck size={14} /> {t("dealer.verified", "Проверен дилър")}
            </span>
          </div>
          <div className="mt-2 flex items-center gap-4 text-sm text-[hsl(var(--ink-muted))] flex-wrap">
            {dealer.city && (
              <span className="inline-flex items-center gap-1">
                <MapPin size={14} /> {dealer.city}{dealer.country ? `, ${dealer.country}` : ""}
              </span>
            )}
            {rating?.count > 0 && (
              <span className="inline-flex items-center gap-1" data-testid="dealer-rating">
                <Star size={14} className="fill-current" /> {rating.avg.toFixed(1)} ({rating.count})
              </span>
            )}
            <span>
              {t("dealer.sold_total", "Продадени: {{n}}", { n: counts?.sold_total ?? 0 })}
            </span>
          </div>
          {dealer.bio && (
            <p className="mt-3 text-sm text-[hsl(var(--ink-muted))] max-w-2xl whitespace-pre-line">
              {dealer.bio}
            </p>
          )}
        </div>
      </div>

      {/* Active listings */}
      <section className="mt-10">
        <div className="flex items-baseline justify-between mb-4">
          <h2 className="font-serif text-2xl">
            {t("dealer.active_listings", "Активни обяви")}
          </h2>
          <span className="text-sm text-[hsl(var(--ink-muted))]" data-testid="dealer-active-count">
            {counts?.active ?? 0}
          </span>
        </div>
        {active_listings?.length > 0 ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5" data-testid="dealer-active-grid">
            {active_listings.map((a) => <AuctionCard key={a.id} auction={a} />)}
          </div>
        ) : (
          <p className="text-[hsl(var(--ink-muted))]">
            {t("dealer.no_active", "Няма активни обяви в момента.")}
          </p>
        )}
      </section>

      {/* Recently sold */}
      {recently_sold?.length > 0 && (
        <section className="mt-12">
          <h2 className="font-serif text-2xl mb-4">
            {t("dealer.recently_sold", "Наскоро продадени")}
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5" data-testid="dealer-sold-grid">
            {recently_sold.map((a) => <AuctionCard key={a.id} auction={a} />)}
          </div>
        </section>
      )}
    </div>
  );
}
