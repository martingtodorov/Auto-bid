import React, { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { Award, ShoppingBag, Calendar, TrendingUp, AlertCircle } from "lucide-react";
import { api, formatEUR } from "../lib/apiClient";
import AuctionCard from "../components/AuctionCard";

export default function ProfilePage() {
  const { userId } = useParams();
  const [data, setData] = useState(null);
  const [tab, setTab] = useState("sales");
  const [err, setErr] = useState("");

  useEffect(() => {
    api.get(`/users/${userId}/profile`)
      .then((r) => setData(r.data))
      .catch((e) => setErr(e?.response?.data?.detail || "Грешка"));
  }, [userId]);

  if (err) return (
    <main className="py-24 text-center" data-testid="profile-error">
      <AlertCircle size={32} className="mx-auto text-[hsl(var(--danger))]" />
      <h1 className="font-serif text-3xl mt-4">{err}</h1>
    </main>
  );
  if (!data) return <div className="py-24 text-center">Зареждане…</div>;

  const { user, stats, listings_sold, purchases, active_listings } = data;
  const memberYear = new Date(user.member_since).getFullYear();
  const list = tab === "sales" ? listings_sold : tab === "purchases" ? purchases : active_listings;

  return (
    <main data-testid="profile-page">
      <section className="rule-b hero-ambient">
        <div className="max-w-[1200px] mx-auto px-4 sm:px-6 lg:px-10 py-16">
          <div className="flex items-start gap-8 flex-wrap">
            <div className="w-24 h-24 rounded-full bg-[hsl(var(--ink))] text-white flex items-center justify-center font-serif text-3xl shrink-0">
              {user.name.charAt(0).toUpperCase()}
            </div>
            <div className="flex-1 min-w-[260px]">
              <div className="overline text-[hsl(var(--accent))]">{user.role === "admin" ? "AutoBid.bg екип" : "Член на общността"}</div>
              <h1 className="font-serif text-4xl lg:text-5xl tracking-tight mt-3">{user.name}</h1>
              <div className="mt-3 text-sm text-[hsl(var(--ink-muted))] flex items-center gap-4 flex-wrap">
                <span className="flex items-center gap-1.5"><Calendar size={13} /> Член от {memberYear}</span>
                {stats.sales_count > 0 && <span className="flex items-center gap-1.5"><Award size={13} /> {stats.sales_count} продажби</span>}
                {stats.purchases_count > 0 && <span className="flex items-center gap-1.5"><ShoppingBag size={13} /> {stats.purchases_count} покупки</span>}
              </div>
            </div>
          </div>

          <div className="mt-10 grid grid-cols-2 md:grid-cols-4 gap-0 border border-[hsl(var(--line))] bg-white rounded-card overflow-hidden">
            <Stat icon={Award} label="Продажби" value={stats.sales_count} sub={formatEUR(stats.sales_total_eur)} />
            <Stat icon={ShoppingBag} label="Покупки" value={stats.purchases_count} sub={formatEUR(stats.purchases_total_eur)} last />
            <Stat icon={TrendingUp} label="Активни" value={stats.active_count} sub="обяви" />
            <Stat icon={Calendar} label="Рейтинг" value="5.0" sub="100% приключили сделки" last />
          </div>
        </div>
      </section>

      <section>
        <div className="max-w-[1200px] mx-auto px-4 sm:px-6 lg:px-10 py-14">
          <div className="inline-flex rounded-card border border-[hsl(var(--line))] overflow-hidden bg-white">
            {[
              { k: "sales", l: `Продажби (${listings_sold.length})` },
              { k: "purchases", l: `Покупки (${purchases.length})` },
              { k: "active", l: `Активни (${active_listings.length})` },
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
            {list.length === 0 ? (
              <div className="py-24 text-center rounded-card border border-[hsl(var(--line))]" data-testid="profile-empty">
                <p className="font-serif text-2xl">
                  {tab === "sales" ? "Все още няма продажби" : tab === "purchases" ? "Все още няма покупки" : "Няма активни обяви"}
                </p>
                <p className="mt-2 text-sm text-[hsl(var(--ink-muted))]">Историята ще се появи тук.</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6 stagger" data-testid="profile-grid">
                {list.map((a) => <AuctionCard key={a.id} auction={a} />)}
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
