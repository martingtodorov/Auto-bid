import React, { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Award, ShoppingBag, Calendar, TrendingUp, AlertCircle, Star } from "lucide-react";
import { api, formatEUR } from "../lib/apiClient";
import AuctionCard from "../components/AuctionCard";
import SellerReviews, { StarRating } from "../components/SellerReviews";
import FollowButton from "../components/FollowButton";
import { setPageMeta, combineJsonLd, buildBreadcrumbs } from "../lib/seo";
import { useBrandName } from "../lib/brand";

export default function ProfilePage() {
  const { t } = useTranslation();
  const { userId } = useParams();
  const brand = useBrandName();
  const [data, setData] = useState(null);
  const [tab, setTab] = useState("sales");
  const [reviewCount, setReviewCount] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    api.get(`/users/${userId}/profile`)
      .then((r) => setData(r.data))
      .catch((e) => setErr(e?.response?.data?.detail || "Грешка"));
  }, [userId]);

  // Fetch review count separately so the tab label stays accurate if the user
  // posts one inline. The URL param might be a slug, so wait for the profile
  // response to resolve the real user id before querying review endpoints.
  const resolvedUserId = data?.user?.id;
  useEffect(() => {
    if (!resolvedUserId) return;
    api.get(`/users/${resolvedUserId}/rating`)
      .then((r) => setReviewCount(r.data?.count ?? 0))
      .catch(() => setReviewCount(0));
  }, [resolvedUserId]);

  // SEO + JSON-LD (Person + AggregateRating when reviews exist)
  useEffect(() => {
    if (!data) return;
    const { user, stats, rating } = data;
    const count = rating?.count ?? 0;
    const avg = rating?.avg ?? 0;
    const title = `${user.name} — Профил на ${user.role === "admin" ? "autoandbid екип" : "продавач"} | autoandbid.com`;
    const desc = count > 0
      ? `${user.name} — ${avg.toFixed(1)}/5 (${count} отзива), ${stats.sales_count} продажби в autoandbid.com. Виж активни обяви и история на сделките.`
      : `${user.name} — ${stats.sales_count} продажби, ${stats.purchases_count} покупки в autoandbid.com. Профил и история на сделките.`;
    const url = window.location.href;
    const personLd = {
      "@context": "https://schema.org",
      "@type": "Person",
      name: user.name,
      url,
    };
    if (count > 0) {
      personLd.aggregateRating = {
        "@type": "AggregateRating",
        ratingValue: avg,
        reviewCount: count,
        bestRating: 5,
        worstRating: 1,
      };
    }
    const crumbs = buildBreadcrumbs([
      { name: "Начало", url: window.location.origin },
      { name: "Профили", url: `${window.location.origin}/auctions` },
      { name: user.name, url },
    ]);
    setPageMeta({
      title, description: desc, url,
      jsonLd: combineJsonLd(personLd, crumbs),
    });
  }, [data, brand]);

  if (err) return (
    <main className="py-24 text-center" data-testid="profile-error">
      <AlertCircle size={32} className="mx-auto text-[hsl(var(--danger))]" />
      <h1 className="font-serif text-3xl mt-4">{err}</h1>
    </main>
  );
  if (!data) return <div className="py-24 text-center">{t("common.loading")}</div>;

  const { user, stats, listings_sold, purchases, active_listings, rating } = data;
  const memberYear = new Date(user.member_since).getFullYear();
  const effectiveReviewCount = reviewCount ?? rating?.count ?? 0;
  const effectiveAvg = rating?.avg ?? 0;

  const gridList = tab === "sales" ? listings_sold : tab === "purchases" ? purchases : tab === "active" ? active_listings : null;

  return (
    <main data-testid="profile-page">
      <section className="rule-b hero-ambient">
        <div className="max-w-[1200px] mx-auto px-4 sm:px-6 lg:px-10 py-16">
          <div className="flex items-start gap-8 flex-wrap">
            <div className="w-24 h-24 rounded-full bg-[hsl(var(--ink))] text-white flex items-center justify-center font-serif text-3xl shrink-0">
              {user.name.charAt(0).toUpperCase()}
            </div>
            <div className="flex-1 min-w-[260px]">
              <div className="overline text-[hsl(var(--accent))]">{user.role === "admin" ? `${brand} екип` : "Член на общността"}</div>
              <div className="flex items-center gap-3 flex-wrap mt-3">
                <h1 className="font-serif text-4xl lg:text-5xl tracking-tight">{user.name}</h1>
                <FollowButton userId={user.id} />
              </div>
              <div className="mt-3 text-sm text-[hsl(var(--ink-muted))] flex items-center gap-4 flex-wrap">
                <span className="flex items-center gap-1.5"><Calendar size={13} /> Член от {memberYear}</span>
                {stats.sales_count > 0 && <span className="flex items-center gap-1.5"><Award size={13} /> {stats.sales_count} продажби</span>}
                {stats.purchases_count > 0 && <span className="flex items-center gap-1.5"><ShoppingBag size={13} /> {stats.purchases_count} покупки</span>}
                {effectiveReviewCount > 0 && (
                  <button
                    onClick={() => setTab("reviews")}
                    className="flex items-center gap-1.5 hover:text-[hsl(var(--ink))] transition-colors"
                    data-testid="profile-rating-pill"
                  >
                    <StarRating value={effectiveAvg} size={12} />
                    <span>{effectiveAvg.toFixed(1)} ({effectiveReviewCount})</span>
                  </button>
                )}
              </div>
            </div>
          </div>

          <div className="mt-10 grid grid-cols-2 md:grid-cols-4 gap-0 border border-[hsl(var(--line))] bg-white rounded-card overflow-hidden">
            <Stat icon={Award} label="Продажби" value={stats.sales_count} sub={formatEUR(stats.sales_total_eur)} />
            <Stat icon={ShoppingBag} label="Покупки" value={stats.purchases_count} sub={formatEUR(stats.purchases_total_eur)} />
            <Stat icon={TrendingUp} label="Активни" value={stats.active_count} sub="обяви" />
            <Stat
              icon={Star}
              label="Рейтинг"
              value={effectiveReviewCount > 0 ? effectiveAvg.toFixed(1) : "—"}
              sub={effectiveReviewCount > 0 ? `${effectiveReviewCount} ${effectiveReviewCount === 1 ? "отзив" : "отзива"}` : "Все още няма отзиви"}
              last
            />
          </div>
        </div>
      </section>

      <section>
        <div className="max-w-[1200px] mx-auto px-4 sm:px-6 lg:px-10 py-14">
          <div className="inline-flex rounded-card border border-[hsl(var(--line))] overflow-hidden bg-white flex-wrap">
            {[
              { k: "sales", l: `Продажби (${listings_sold.length})` },
              { k: "purchases", l: `Покупки (${purchases.length})` },
              { k: "active", l: `Активни (${active_listings.length})` },
              { k: "reviews", l: `Отзиви (${effectiveReviewCount})` },
            ].map((o, i) => (
              <button
                key={o.k}
                onClick={() => setTab(o.k)}
                className={`px-5 py-2.5 text-sm font-medium ${i > 0 ? "border-l border-[hsl(var(--line))]" : ""} ${tab === o.k ? "bg-[hsl(var(--ink))] text-white" : ""}`}
                data-testid={`profile-tab-${o.k}`}
              >{o.l}</button>
            ))}
          </div>

          <div className="mt-10">
            {tab === "reviews" ? (
              <SellerReviews sellerId={user.id} rating={rating} />
            ) : gridList && gridList.length === 0 ? (
              <div className="py-24 text-center rounded-card border border-[hsl(var(--line))]" data-testid="profile-empty">
                <p className="font-serif text-2xl">
                  {tab === "sales" ? "Все още няма продажби" : tab === "purchases" ? "Все още няма покупки" : "Няма активни обяви"}
                </p>
                <p className="mt-2 text-sm text-[hsl(var(--ink-muted))]">Историята ще се появи тук.</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6 stagger" data-testid="profile-grid">
                {gridList.map((a) => <AuctionCard key={a.id} auction={a} />)}
              </div>
            )}
          </div>
        </div>
      </section>
    </main>
  );
}

function Stat({ icon: Icon, label, value, sub, last }) {
  return (
    <div className={`p-6 ${last ? "" : "border-r border-[hsl(var(--line))]"} border-b md:border-b-0 last:border-r-0`}>
      <Icon size={16} className="text-[hsl(var(--accent))]" />
      <div className="overline text-[hsl(var(--ink-muted))] mt-3">{label}</div>
      <div className="font-serif text-3xl mt-1">{value}</div>
      <div className="text-xs text-[hsl(var(--ink-muted))] mt-1">{sub}</div>
    </div>
  );
}
