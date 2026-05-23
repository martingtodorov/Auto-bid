import React, { useEffect, useState } from "react";
import { Navigate, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../lib/auth";
import { api, formatEUR } from "../lib/apiClient";
import { auctionUrl } from "../lib/auctionUrl";
import { usePrivatePageMeta } from "../lib/usePrivatePageMeta";
import { useBrandName } from "../lib/brand";

export default function DashboardPage() {
  const { t, i18n } = useTranslation();
  const brand = useBrandName();
  const { user, loading } = useAuth();
  const [bids, setBids] = useState([]);
  usePrivatePageMeta({ titleKey: "page_meta.dashboard_title", descKey: "page_meta.dashboard_desc", brand });

  useEffect(() => {
    if (!user) return;
    api.get("/me/bids").then((r) => setBids(r.data));
  }, [user]);

  if (loading) return <div className="py-24 text-center">{t("common.loading")}</div>;
  if (!user) return <Navigate to="/login?next=/dashboard" replace />;

  return (
    <main data-testid="dashboard-page">
      <div className="max-w-[1200px] mx-auto px-4 sm:px-6 lg:px-10 py-16">
        <div className="overline text-[hsl(var(--accent))]">{t("dashboard.overline", "Профил")}</div>
        <h1 className="font-serif text-4xl mt-3">{t("dashboard.greeting", "Здравейте, {{name}}", { name: user.name })}</h1>
        <p className="mt-2 text-sm text-[hsl(var(--ink-muted))]">{user.email}</p>

        <div className="mt-12 grid grid-cols-1 md:grid-cols-3 gap-0 border border-[hsl(var(--line))] bg-white">
          <div className="p-6 border-b md:border-b-0 md:border-r border-[hsl(var(--line))]">
            <div className="overline text-[hsl(var(--ink-muted))]">{t("dashboard.stats.bids", "Наддавания")}</div>
            <div className="font-serif text-4xl mt-2">{bids.length}</div>
          </div>
          <div className="p-6 border-b md:border-b-0 md:border-r border-[hsl(var(--line))]">
            <div className="overline text-[hsl(var(--ink-muted))]">{t("dashboard.stats.active", "Активни търгове")}</div>
            <div className="font-serif text-4xl mt-2">—</div>
          </div>
          <div className="p-6">
            <div className="overline text-[hsl(var(--ink-muted))]">{t("dashboard.stats.won", "Печеливши")}</div>
            <div className="font-serif text-4xl mt-2">—</div>
          </div>
        </div>

        <div className="mt-14">
          <h2 className="font-serif text-2xl">{t("dashboard.history_title", "История на моите наддавания")}</h2>
          <div className="mt-6 border border-[hsl(var(--line))]">
            {bids.length === 0 ? (
              <div className="p-8 text-center text-[hsl(var(--ink-muted))] text-sm">
                {t("dashboard.empty_bids", "Все още нямате наддавания.")} <Link to="/auctions" className="underline">{t("dashboard.browse_auctions", "Разгледайте търговете →")}</Link>
              </div>
            ) : (
              bids.map((b) => (
                <div key={b.id} className="p-4 rule-b last:border-b-0 flex justify-between items-center">
                  <div>
                    <Link to={auctionUrl({ id: b.auction_id, title: b.auction_title })} className="text-sm underline">{t("dashboard.auction_link", "Търг #{{id}}", { id: b.auction_id.slice(0, 8) })}</Link>
                    <div className="text-xs text-[hsl(var(--ink-muted))] font-mono mt-1">{new Date(b.created_at).toLocaleString(i18n.language)}</div>
                  </div>
                  <div className="font-serif text-xl">{formatEUR(b.amount_eur)}</div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </main>
  );
}
