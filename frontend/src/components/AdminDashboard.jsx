import React, { useEffect, useState } from "react";
import { TrendingUp, Clock, DollarSign, Users, Car, Activity, ShieldCheck, Gavel } from "lucide-react";
import { api, formatEUR } from "../lib/apiClient";
import { formatError } from "../lib/auth";

export default function AdminDashboard() {
  const [stats, setStats] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    (async () => {
      try { const { data } = await api.get("/admin/stats"); setStats(data); }
      catch (e) { setErr(formatError(e)); }
    })();
  }, []);

  if (err) return <div className="py-10 text-sm text-[hsl(var(--danger))]" data-testid="dashboard-error">{err}</div>;
  if (!stats) return <div className="py-10 text-center text-[hsl(var(--ink-muted))]">Зареждане…</div>;

  return (
    <div className="mt-10 space-y-8" data-testid="admin-dashboard">
      {/* Revenue */}
      <section>
        <div className="overline text-[hsl(var(--accent))] mb-3">Приходи</div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <Stat
            icon={DollarSign}
            label="GMV (общо)"
            value={formatEUR(stats.revenue.gmv_all_time)}
            sub={`${stats.revenue.sold_count} продажби`}
            accent
            tid="stat-gmv"
          />
          <Stat
            icon={TrendingUp}
            label="Приходи комисионна"
            value={formatEUR(stats.revenue.commission_all_time)}
            sub="2% от всяка сделка"
            accent
            tid="stat-commission"
          />
          <Stat
            icon={Activity}
            label="GMV · последни 30 дни"
            value={formatEUR(stats.revenue.gmv_last_30d)}
            tid="stat-gmv-30d"
          />
          <Stat
            icon={TrendingUp}
            label="Комисионна · 30 дни"
            value={formatEUR(stats.revenue.commission_last_30d)}
            tid="stat-commission-30d"
          />
        </div>
      </section>

      {/* Auctions */}
      <section>
        <div className="overline text-[hsl(var(--accent))] mb-3">Обяви</div>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
          <Stat icon={Car} label="Всички" value={stats.auctions.total} tid="stat-auctions-total" />
          <Stat icon={Clock} label="Очакващи" value={stats.auctions.pending} tid="stat-auctions-pending" highlight={stats.auctions.pending > 0} />
          <Stat icon={Gavel} label="Активни" value={stats.auctions.live} tid="stat-auctions-live" />
          <Stat icon={DollarSign} label="Продадени" value={stats.auctions.sold} tid="stat-auctions-sold" />
          <Stat icon={Activity} label="Резерв не е достигнат" value={stats.auctions.reserve_not_met} tid="stat-auctions-reserve" />
          <Stat icon={Car} label="Премахнати" value={stats.auctions.removed} tid="stat-auctions-removed" />
        </div>
      </section>

      {/* Users + Bids */}
      <section>
        <div className="overline text-[hsl(var(--accent))] mb-3">Потребители и наддавания</div>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
          <Stat icon={Users} label="Общо потребители" value={stats.users.total} tid="stat-users-total" />
          <Stat icon={Users} label="Нови · тази седмица" value={stats.users.new_this_week} tid="stat-users-new" highlight={stats.users.new_this_week > 0} />
          <Stat icon={ShieldCheck} label="Проверени дилъри" value={stats.users.verified_dealers} tid="stat-users-dealers" />
          <Stat icon={Gavel} label="Наддавания общо" value={stats.bids.total} tid="stat-bids-total" />
          <Stat icon={Activity} label="Наддавания · седмица" value={stats.bids.this_week} tid="stat-bids-week" />
        </div>
      </section>
    </div>
  );
}

function Stat({ icon: Icon, label, value, sub, accent, highlight, tid }) {
  return (
    <div
      className={`rounded-card border p-4 bg-white transition ${accent ? "border-[hsl(var(--accent))]/30 bg-[hsl(var(--accent-soft))]" : "border-[hsl(var(--line))]"} ${highlight ? "ring-2 ring-[hsl(var(--accent))]/40" : ""}`}
      data-testid={tid}
    >
      <div className="flex items-center gap-2 text-[hsl(var(--ink-muted))]">
        <Icon size={14} />
        <span className="text-xs font-semibold uppercase tracking-wide">{label}</span>
      </div>
      <div className="mt-2 font-serif text-2xl lg:text-3xl">{value}</div>
      {sub && <div className="text-[11px] text-[hsl(var(--ink-muted))] mt-1">{sub}</div>}
    </div>
  );
}
