import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { TrendingUp, BarChart3, Calendar, Crown, Search } from "lucide-react";
import { useTranslation } from "react-i18next";
import { api, formatEUR, formatKM } from "../lib/apiClient";
import AuctionCard from "../components/AuctionCard";
import { setPageMeta, combineJsonLd, buildBreadcrumbs } from "../lib/seo";
import { useAuth } from "../lib/auth";
import { translateEnum } from "../lib/carTranslations";

const WINDOW_OPTIONS = [
  { days: 30, label: "30 дни" },
  { days: 90, label: "90 дни" },
  { days: 365, label: "12 месеца" },
  { days: null, label: "От старт" },
];

export default function SalesPage() {
  const { t, i18n } = useTranslation();
  const brand = useBrandName();
  const { user } = useAuth();
  const isPrivileged = user?.role === "admin" || user?.role === "moderator";
  const [stats, setStats] = useState(null);
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [windowDays, setWindowDays] = useState(365);
  const [filters, setFilters] = useState({ make: "", body_type: "", year_min: "", year_max: "", price_min: "", price_max: "", q: "" });
  const [sort, setSort] = useState("recent");
  const [offset, setOffset] = useState(0);
  const LIMIT = 24;

  // SEO
  useEffect(() => {
    setPageMeta({
      title: `Архив продажби и пазарни статистики — ${brand}`,
      description: `Реални цени на продадени автомобили в ${brand}. Средни цени по марка, месечни тенденции и публичен архив на приключилите сделки.`,
      url: window.location.href,
      jsonLd: combineJsonLd(buildBreadcrumbs([
        { name: "Начало", url: window.location.origin },
        { name: "Продадени", url: window.location.href },
      ])),
    });
  }, [brand]);

  // Stats (admin/moderator only — regular users don't need platform analytics)
  useEffect(() => {
    if (!isPrivileged) { setStats(null); return; }
    const params = windowDays ? { days: windowDays } : {};
    api.get("/stats/sold", { params }).then((r) => setStats(r.data)).catch(() => setStats(null));
  }, [windowDays, isPrivileged]);

  // Facets for filter dropdowns (always available; used as make/body_type options for non-privileged users)
  const [facets, setFacets] = useState({ makes: [], body_types: [] });
  useEffect(() => {
    api.get("/auctions/facets").then((r) => {
      const f = r.data || {};
      setFacets({
        makes: (f.makes || []).map((m) => (typeof m === "string" ? m : m.make || m.name || m.value)).filter(Boolean),
        body_types: (f.body_types || []).map((b) => (typeof b === "string" ? b : b.body_type || b.name || b.value)).filter(Boolean),
      });
    }).catch(() => setFacets({ makes: [], body_types: [] }));
  }, []);

  // List (filtered)
  useEffect(() => {
    setLoading(true);
    const params = { limit: LIMIT, offset, sort };
    Object.entries(filters).forEach(([k, v]) => { if (v !== "" && v !== null) params[k] = v; });
    api.get("/auctions/sold", { params })
      .then((r) => {
        const body = r.data;
        if (Array.isArray(body)) { setItems(body); setTotal(body.length); }
        else { setItems(body.items || []); setTotal(body.total || 0); }
      })
      .finally(() => setLoading(false));
  }, [filters, sort, offset]);

  const onFilterChange = (patch) => { setOffset(0); setFilters((f) => ({ ...f, ...patch })); };
  const resetFilters = () => { setOffset(0); setFilters({ make: "", body_type: "", year_min: "", year_max: "", price_min: "", price_max: "", q: "" }); };

  const topMakeMax = useMemo(() => Math.max(1, ...(stats?.by_make || []).map((m) => m.count)), [stats]);
  const monthMax = useMemo(() => Math.max(1, ...(stats?.by_month || []).map((m) => m.avg_eur)), [stats]);

  return (
    <main data-testid="sales-page">
      {/* Hero / KPIs */}
      <section className="rule-b hero-ambient">
        <div className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-10 py-12 lg:py-14">
          <div className="overline text-[hsl(var(--accent))]">Архив</div>
          <h1 className="font-serif text-4xl lg:text-5xl tracking-tight mt-3" data-testid="sales-title">
            {isPrivileged ? "Архив на продажбите" : "Продадени автомобили"}
          </h1>
          <p className="mt-3 text-sm text-[hsl(var(--ink-muted))] max-w-2xl">
            {isPrivileged
              ? "Прозрачни цени на реално продадени автомобили — средни стойности, месечни тенденции и топ марки."
              : "Разгледайте приключилите успешно търгове — подбрани, документирани и предадени на новите им собственици."}
          </p>

          {isPrivileged && (
            <>
              {/* Window toggle */}
              <div className="mt-6 inline-flex rounded-card border border-[hsl(var(--line))] overflow-hidden bg-white" data-testid="stats-window-toggle">
                {WINDOW_OPTIONS.map((o, i) => (
                  <button
                    key={o.label}
                    onClick={() => setWindowDays(o.days)}
                    className={`px-4 py-2 text-xs font-medium ${i > 0 ? "border-l border-[hsl(var(--line))]" : ""} ${windowDays === o.days ? "bg-[hsl(var(--ink))] text-white" : "hover:bg-[hsl(var(--surface))]"}`}
                    data-testid={`stats-window-${o.days || "all"}`}
                  >{o.label}</button>
                ))}
              </div>

              {/* KPIs */}
              <div className="mt-8 grid grid-cols-2 md:grid-cols-4 gap-0 border border-[hsl(var(--line))] bg-white rounded-card overflow-hidden" data-testid="sales-kpis">
                <KPI label="Приключили сделки" value={stats ? stats.total_count : "—"} sub={stats?.total_count ? "продадени автомобили" : "няма данни"} />
                <KPI label="Общ обем" value={stats ? formatEUR(stats.total_volume_eur) : "—"} sub="стойност на сделките" />
                <KPI label="Средна цена" value={stats ? formatEUR(stats.avg_price_eur) : "—"} sub={stats ? `медиана ${formatEUR(stats.median_price_eur)}` : "—"} />
                <KPI label="Най-висока продажба" value={stats ? formatEUR(stats.max_price_eur) : "—"} sub={stats?.highest_sale?.title || "—"} last />
              </div>

              {/* Highest sale spotlight */}
              {stats?.highest_sale && (
                <Link
                  to={`/auctions/${stats.highest_sale.id}`}
                  className="mt-6 flex items-center gap-4 rounded-card border border-[hsl(var(--line))] bg-white p-3 pr-5 group hover:border-[hsl(var(--accent))] transition-colors"
                  data-testid="highest-sale-card"
                >
                  <div className="w-24 h-16 overflow-hidden rounded-card shrink-0 bg-[hsl(var(--surface))]">
                    {stats.highest_sale.images?.[0] && (
                      <img src={stats.highest_sale.images[0]} alt={stats.highest_sale.title} className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105" />
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5 overline text-[hsl(var(--accent))]"><Crown size={12} /> Рекорд за периода</div>
                    <div className="font-serif text-lg mt-1 truncate">{stats.highest_sale.title}</div>
                  </div>
                  <div className="font-serif text-2xl text-right">{formatEUR(stats.highest_sale.current_bid_eur)}</div>
                </Link>
              )}
            </>
          )}
        </div>
      </section>

      {/* Charts — admin/moderator only */}
      {isPrivileged && (
        <section className="rule-b" data-testid="sales-charts-section">
          <div className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-10 py-14 grid grid-cols-1 lg:grid-cols-2 gap-8">
            <div className="rounded-card border border-[hsl(var(--line))] bg-white p-6" data-testid="chart-by-make">
              <div className="flex items-center gap-2 overline text-[hsl(var(--accent))]"><BarChart3 size={14} /> Топ марки</div>
              <h2 className="font-serif text-2xl mt-2">По брой сделки</h2>
              <ul className="mt-5 space-y-2.5">
                {(stats?.by_make || []).map((m) => (
                  <li key={m.make} className="flex items-center gap-3">
                    <span className="w-24 text-sm font-medium truncate">{m.make}</span>
                    <div className="flex-1 h-2.5 rounded-full bg-[hsl(var(--surface))] border border-[hsl(var(--line))] overflow-hidden">
                      <div className="h-full bg-[hsl(var(--accent))]" style={{ width: `${(m.count / topMakeMax) * 100}%` }} />
                    </div>
                    <span className="text-xs w-16 text-right font-mono">{m.count}</span>
                    <span className="text-xs w-24 text-right text-[hsl(var(--ink-muted))] hidden sm:block">{formatEUR(m.avg_eur)}</span>
                  </li>
                ))}
                {!stats?.by_make?.length && <li className="text-sm text-[hsl(var(--ink-muted))]">Няма данни за избрания период.</li>}
              </ul>
            </div>

            <div className="rounded-card border border-[hsl(var(--line))] bg-white p-6" data-testid="chart-monthly">
              <div className="flex items-center gap-2 overline text-[hsl(var(--accent))]"><Calendar size={14} /> Месечна тенденция</div>
              <h2 className="font-serif text-2xl mt-2">Средна цена</h2>
              <div className="mt-5 flex items-end gap-1.5 h-40">
                {(stats?.by_month || []).map((m) => (
                  <div key={m.month} className="flex-1 flex flex-col items-center justify-end group" title={`${m.month}: ${formatEUR(m.avg_eur)} (${m.count} сделки)`}>
                    <div
                      className="w-full bg-[hsl(var(--ink))] group-hover:bg-[hsl(var(--accent))] transition-colors rounded-t"
                      style={{ height: `${(m.avg_eur / monthMax) * 100}%`, minHeight: "2px" }}
                    />
                    <span className="mt-1 text-[10px] text-[hsl(var(--ink-muted))] font-mono">{m.month.slice(5)}</span>
                  </div>
                ))}
                {!stats?.by_month?.length && <div className="w-full text-sm text-[hsl(var(--ink-muted))]">Няма данни.</div>}
              </div>
            </div>
          </div>
        </section>
      )}

      {/* Filters + List */}
      <section className="rule-b bg-[hsl(var(--surface))]">
        <div className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-10 py-14">
          <div className="flex items-end justify-between gap-4 flex-wrap">
            <div>
              <div className="overline text-[hsl(var(--accent))]">Всички сделки</div>
              <h2 className="font-serif text-3xl lg:text-4xl tracking-tight mt-3">Последни продажби {total ? `(${total})` : ""}</h2>
            </div>
            <select
              value={sort}
              onChange={(e) => { setOffset(0); setSort(e.target.value); }}
              className="border border-[hsl(var(--line))] rounded-card px-3 py-2 bg-white text-sm"
              data-testid="sales-sort"
            >
              <option value="recent">Най-скорошни</option>
              <option value="oldest">Най-стари</option>
              <option value="price_desc">Цена ↓</option>
              <option value="price_asc">Цена ↑</option>
            </select>
          </div>

          {/* Filter bar */}
          <div className="mt-6 rounded-card border border-[hsl(var(--line))] bg-white p-4 grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3" data-testid="sales-filters">
            <div className="col-span-2 md:col-span-4 lg:col-span-2 relative">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[hsl(var(--ink-muted))]" />
              <input
                value={filters.q}
                onChange={(e) => onFilterChange({ q: e.target.value })}
                placeholder="Търси по марка / модел…"
                className="w-full border border-[hsl(var(--line))] rounded-card pl-9 pr-3 py-2 text-sm"
                data-testid="sales-filter-q"
              />
            </div>
            <select value={filters.make} onChange={(e) => onFilterChange({ make: e.target.value })} className="border border-[hsl(var(--line))] rounded-card px-2 py-2 text-sm bg-white" data-testid="sales-filter-make">
              <option value="">{t("auctions_page.make")}</option>
              {(stats?.by_make?.length ? stats.by_make.map((m) => m.make) : facets.makes).map((name) => (
                <option key={name} value={name}>{name}</option>
              ))}
            </select>
            <select value={filters.body_type} onChange={(e) => onFilterChange({ body_type: e.target.value })} className="border border-[hsl(var(--line))] rounded-card px-2 py-2 text-sm bg-white" data-testid="sales-filter-body">
              <option value="">{t("auctions_page.body_type")}</option>
              {(stats?.by_body_type?.length ? stats.by_body_type.map((b) => b.body_type) : facets.body_types).map((name) => (
                <option key={name} value={name}>{translateEnum(name, "body_type", i18n.language)}</option>
              ))}
            </select>
            <input type="number" placeholder={t("auctions_page.year_from")} value={filters.year_min} onChange={(e) => onFilterChange({ year_min: e.target.value })} className="border border-[hsl(var(--line))] rounded-card px-2 py-2 text-sm" data-testid="sales-filter-year-min" />
            <input type="number" placeholder={t("auctions_page.price_to_eur")} value={filters.price_max} onChange={(e) => onFilterChange({ price_max: e.target.value })} className="border border-[hsl(var(--line))] rounded-card px-2 py-2 text-sm" data-testid="sales-filter-price-max" />
            <button
              onClick={resetFilters}
              className="border border-[hsl(var(--line))] rounded-card px-3 py-2 text-sm bg-white hover:bg-[hsl(var(--surface))]"
              data-testid="sales-filter-reset"
            >Изчисти</button>
          </div>

          {/* List */}
          <div className="mt-8">
            {loading ? (
              <div className="py-20 text-center text-sm text-[hsl(var(--ink-muted))]">Зареждане…</div>
            ) : items.length === 0 ? (
              <div className="py-20 text-center rounded-card border border-[hsl(var(--line))] bg-white" data-testid="sales-empty">
                <TrendingUp size={28} className="mx-auto text-[hsl(var(--ink-muted))]" />
                <p className="font-serif text-xl mt-3">Няма намерени сделки</p>
                <p className="mt-1 text-sm text-[hsl(var(--ink-muted))]">Променете филтрите, за да видите повече.</p>
              </div>
            ) : (
              <>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6 stagger" data-testid="sales-grid">
                  {items.map((a) => <AuctionCard key={a.id} auction={a} compact />)}
                </div>
                {total > LIMIT && (
                  <div className="mt-10 flex items-center justify-between" data-testid="sales-pagination">
                    <span className="text-sm text-[hsl(var(--ink-muted))]">Показани {offset + 1}–{Math.min(offset + items.length, total)} от {total}</span>
                    <div className="flex gap-2">
                      <button
                        disabled={offset === 0}
                        onClick={() => setOffset((o) => Math.max(0, o - LIMIT))}
                        className="px-3 py-1.5 border border-[hsl(var(--line))] rounded-card text-sm bg-white disabled:opacity-40"
                      >Предишна</button>
                      <button
                        disabled={offset + LIMIT >= total}
                        onClick={() => setOffset((o) => o + LIMIT)}
                        className="px-3 py-1.5 border border-[hsl(var(--line))] rounded-card text-sm bg-white disabled:opacity-40"
                      >Следваща</button>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </section>
    </main>
  );
}

function KPI({ label, value, sub, last }) {
  return (
    <div className={`p-6 ${last ? "" : "border-r border-[hsl(var(--line))]"} border-b md:border-b-0 last:border-r-0`}>
      <div className="overline text-[hsl(var(--ink-muted))]">{label}</div>
      <div className="font-serif text-2xl lg:text-3xl mt-2 truncate">{value}</div>
      <div className="text-xs text-[hsl(var(--ink-muted))] mt-1 truncate">{sub}</div>
    </div>
  );
}
