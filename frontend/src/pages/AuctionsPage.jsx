import React, { useEffect, useState, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../lib/apiClient";
import { useAuth, formatError } from "../lib/auth";
import AuctionCard from "../components/AuctionCard";
import Pagination from "../components/Pagination";
import { SlidersHorizontal, X, Search, BookmarkPlus, Check } from "lucide-react";
import { mergeMakes } from "../lib/makes";
import { translateEnum } from "../lib/carTranslations";
import { setPageMeta, resetPageMeta, buildBreadcrumbs } from "../lib/seo";
import { useBrandName } from "../lib/brand";

export default function AuctionsPage() {
  const { t, i18n } = useTranslation();
  const brand = useBrandName();
  const { user } = useAuth();
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const PAGE_SIZE = 20;
  const [loading, setLoading] = useState(true);
  const [facets, setFacets] = useState({ makes: [], fuels: [], transmissions: [], body_types: [] });
  const [saveMsg, setSaveMsg] = useState("");
  const [saveErr, setSaveErr] = useState("");
  const [filters, setFilters] = useState({
    make: "", fuel: "", transmission: "", body_type: "",
    min_price: "", max_price: "", year_min: "", year_max: "", status: "live", sort: "ending_soon",
    q: "",
  });
  const [open, setOpen] = useState(false);

  useEffect(() => {
    api.get("/auctions/facets").then((r) => setFacets(r.data));
    const params = new URLSearchParams(window.location.search);
    const q = params.get("q");
    if (q) setFilters((p) => ({ ...p, q, status: "" }));
  }, []);

  useEffect(() => {
    setPageMeta({
      title: `${t("seo.all_auctions_title", "All auctions")} — ${brand}`,
      description: t("seo.all_auctions_description", `Browse all active car auctions on ${brand} — filter by make, year, fuel and price.`),
      url: window.location.href,
      jsonLd: buildBreadcrumbs([
        { name: t("nav.home", "Home"), url: window.location.origin + "/" },
        { name: t("nav.auctions", "Auctions"), url: window.location.origin + "/auctions" },
      ]),
    });
    return () => resetPageMeta();
  }, [brand, t]);

  const load = useCallback(async () => {
    setLoading(true);
    const params = Object.fromEntries(Object.entries(filters).filter(([, v]) => v !== "" && v != null));
    params.paginated = 1;
    params.limit = PAGE_SIZE;
    params.offset = (page - 1) * PAGE_SIZE;
    const { data } = await api.get("/auctions", { params });
    setItems(data?.items || []);
    setTotal(data?.total || 0);
    setLoading(false);
    // Scroll to grid top after a page change
    if (page > 1) {
      try {
        document.querySelector('[data-testid="auctions-grid"]')?.scrollIntoView({ behavior: "smooth", block: "start" });
      } catch (_) { /* noop */ }
    }
  }, [filters, page]);

  // Reset to page 1 when filters change
  useEffect(() => { setPage(1); }, [filters]);

  useEffect(() => { load(); }, [load]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const reset = () => setFilters({ make: "", fuel: "", transmission: "", body_type: "", min_price: "", max_price: "", year_min: "", year_max: "", status: "live", sort: "ending_soon", q: "" });
  const set = (k, v) => setFilters((p) => ({ ...p, [k]: v }));

  const saveSearch = async () => {
    if (!user) { window.location.href = "/login?next=/auctions"; return; }
    setSaveMsg(""); setSaveErr("");
    const f = Object.fromEntries(Object.entries(filters).filter(([k, v]) => v !== "" && v != null && k !== "sort" && k !== "status"));
    const name = window.prompt("Име на търсенето:", filters.q || filters.make || "Ново търсене");
    if (!name) return;
    try {
      await api.post("/me/saved-searches", { name: name.trim(), filters: f });
      setSaveMsg("Записано. Ще получите имейл при нова съвпадаща обява.");
      setTimeout(() => setSaveMsg(""), 4000);
    } catch (e) { setSaveErr(formatError(e)); }
  };

  const Select = ({ k, label, options, kind }) => (
    <div>
      <label className="overline text-[hsl(var(--ink-muted))] block mb-2">{label}</label>
      <select value={filters[k]} onChange={(e) => set(k, e.target.value)} className="w-full border border-[hsl(var(--line))] h-10 px-3 text-sm bg-white" data-testid={`filter-${k}`}>
        <option value="">{t("auctions_page.all")}</option>
        {options.map((o) => <option key={o} value={o}>{kind ? translateEnum(o, kind, i18n.language) : o}</option>)}
      </select>
    </div>
  );

  const Sidebar = (
    <aside className="bg-white border border-[hsl(var(--line))] p-6 space-y-5 rounded-card">
      <div className="flex items-center justify-between">
        <h2 className="font-serif text-xl">{t("auctions_page.filters")}</h2>
        <button onClick={reset} className="text-xs underline text-[hsl(var(--ink-muted))]" data-testid="reset-filters">{t("auctions_page.clear")}</button>
      </div>

      <Select k="make" label={t("auctions_page.make")} options={mergeMakes(facets.makes)} />
      <Select k="body_type" label={t("auctions_page.body_type")} options={facets.body_types} kind="body_type" />
      <Select k="fuel" label={t("auctions_page.fuel")} options={facets.fuels} kind="fuel" />
      <Select k="transmission" label={t("auctions_page.transmission")} options={facets.transmissions} kind="transmission" />

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="overline text-[hsl(var(--ink-muted))] block mb-2">{t("auctions_page.year_from")}</label>
          <input type="number" value={filters.year_min} onChange={(e) => set("year_min", e.target.value)} className="w-full border border-[hsl(var(--line))] h-10 px-3 text-sm" data-testid="filter-year-min" />
        </div>
        <div>
          <label className="overline text-[hsl(var(--ink-muted))] block mb-2">{t("auctions_page.year_to")}</label>
          <input type="number" value={filters.year_max} onChange={(e) => set("year_max", e.target.value)} className="w-full border border-[hsl(var(--line))] h-10 px-3 text-sm" data-testid="filter-year-max" />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="overline text-[hsl(var(--ink-muted))] block mb-2">{t("auctions_page.price_from_eur")}</label>
          <input type="number" value={filters.min_price} onChange={(e) => set("min_price", e.target.value)} className="w-full border border-[hsl(var(--line))] h-10 px-3 text-sm" data-testid="filter-min-price" />
        </div>
        <div>
          <label className="overline text-[hsl(var(--ink-muted))] block mb-2">{t("auctions_page.price_to_eur")}</label>
          <input type="number" value={filters.max_price} onChange={(e) => set("max_price", e.target.value)} className="w-full border border-[hsl(var(--line))] h-10 px-3 text-sm" data-testid="filter-max-price" />
        </div>
      </div>
    </aside>
  );

  return (
    <main className="rule-b" data-testid="auctions-page">
      <div className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-10 py-12">
        <div className="overline text-[hsl(var(--accent))]">{t("auctions_page.overline")}</div>
        <h1 className="font-serif text-4xl lg:text-5xl tracking-tight mt-3">{t("auctions_page.title")}</h1>

        <div className="mt-6 max-w-2xl relative">
          <Search size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-[hsl(var(--ink-muted))]" />
          <input
            type="text"
            value={filters.q}
            onChange={(e) => set("q", e.target.value)}
            placeholder={t("auctions_page.search_placeholder")}
            className="w-full border border-[hsl(var(--line))] h-12 pl-11 pr-4 text-sm bg-white"
            data-testid="search-input"
          />
          {filters.q && (
            <button onClick={() => set("q", "")} className="absolute right-3 top-1/2 -translate-y-1/2 text-[hsl(var(--ink-muted))] hover:text-[hsl(var(--ink))]" data-testid="clear-search">
              <X size={16} />
            </button>
          )}
        </div>

        <div className="mt-8 flex items-end justify-between mb-8 flex-wrap gap-3">
          <p className="text-sm text-[hsl(var(--ink-muted))]" data-testid="results-count">
            {items.length} {t("auctions_page.results_count")}{filters.q && <> · „<span className="text-[hsl(var(--ink))]">{filters.q}</span>"</>}
            {saveMsg && <span className="ml-3 text-[hsl(var(--accent))] inline-flex items-center gap-1"><Check size={13} /> {saveMsg}</span>}
            {saveErr && <span className="ml-3 text-[hsl(var(--danger))]">{saveErr}</span>}
          </p>
          <div className="flex items-center gap-2 sm:gap-3 w-full sm:w-auto">
            <button onClick={saveSearch} className="btn btn-secondary h-10 !py-0 !px-3 sm:!px-4 flex items-center gap-1.5 text-xs sm:text-sm shrink-0 rounded-card" data-testid="save-search-btn">
              <BookmarkPlus size={14} />
              <span className="hidden sm:inline">{t("auctions_page.save_search")}</span>
              <span className="sm:hidden">{t("forms.save")}</span>
            </button>
            <select
              value={filters.sort}
              onChange={(e) => set("sort", e.target.value)}
              className="border border-[hsl(var(--line))] h-10 px-2 text-xs sm:text-sm bg-[hsl(var(--bg))] rounded-card w-[110px] sm:w-[120px] shrink-0"
              data-testid="sort-select"
            >
              <option value="ending_soon">{t("auctions_page.sort_ending_soon")}</option>
              <option value="newest">{t("auctions_page.sort_newest")}</option>
              <option value="price_asc">{t("auctions_page.sort_lowest_price")}</option>
              <option value="price_desc">{t("auctions_page.sort_highest_price")}</option>
              <option value="most_bids">{t("auctions_page.sort_most_bids")}</option>
            </select>
            <button
              onClick={() => setOpen(true)}
              className="lg:hidden btn btn-primary h-10 !py-0 !px-4 sm:!px-5 flex items-center gap-2 text-sm sm:text-base shrink-0 rounded-card"
              data-testid="open-filters"
            >
              <SlidersHorizontal size={16} />
              <span>{t("auctions_page.filters")}</span>
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
          <div className="hidden lg:block lg:col-span-3">{Sidebar}</div>

          <div className="lg:col-span-9">
            {loading ? (
              <div className="py-20 text-center text-[hsl(var(--ink-muted))]">{t("auctions_page.loading")}</div>
            ) : items.length === 0 ? (
              <div className="py-20 text-center rounded-card border border-[hsl(var(--line))]" data-testid="auctions-empty">
                <p className="font-serif text-2xl">{t("auctions_page.no_results")}</p>
                <p className="text-sm text-[hsl(var(--ink-muted))] mt-2">{t("auctions_page.no_results_hint")}</p>
              </div>
            ) : (
              <>
                <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-6 stagger" data-testid="auctions-grid">
                  {items.map((a) => <AuctionCard key={a.id} auction={a} />)}
                </div>
                <Pagination page={page} totalPages={totalPages} onChange={setPage} />
              </>
            )}
          </div>
        </div>
      </div>

      {open && (
        <div className="fixed inset-0 z-50 bg-black/40 lg:hidden" onClick={() => setOpen(false)}>
          <div className="absolute inset-y-0 right-0 w-[88vw] max-w-sm bg-white overflow-auto" onClick={(e) => e.stopPropagation()}>
            <div className="p-4 flex items-center justify-between rule-b">
              <span className="font-serif text-xl">{t("auctions_page.filters")}</span>
              <button onClick={() => setOpen(false)}><X /></button>
            </div>
            <div className="p-4">{Sidebar}</div>
          </div>
        </div>
      )}
    </main>
  );
}
