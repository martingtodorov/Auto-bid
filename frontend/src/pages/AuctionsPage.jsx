import React, { useEffect, useState, useCallback } from "react";
import { api } from "../lib/apiClient";
import { useAuth, formatError } from "../lib/auth";
import AuctionCard from "../components/AuctionCard";
import { SlidersHorizontal, X, Search, BookmarkPlus, Check } from "lucide-react";
import { mergeMakes } from "../lib/makes";
import { setPageMeta, resetPageMeta, buildBreadcrumbs } from "../lib/seo";

export default function AuctionsPage() {
  const { user } = useAuth();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [facets, setFacets] = useState({ makes: [], fuels: [], transmissions: [], regions: [], body_types: [] });
  const [saveMsg, setSaveMsg] = useState("");
  const [saveErr, setSaveErr] = useState("");
  const [filters, setFilters] = useState({
    make: "", fuel: "", transmission: "", region: "", body_type: "",
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
      title: "Всички търгове — AutoBid.bg",
      description: "Разгледайте всички активни автомобилни търгове в AutoBid.bg — филтрирайте по марка, година, регион, гориво и цена.",
      url: window.location.href,
      jsonLd: buildBreadcrumbs([
        { name: "Начало", url: window.location.origin + "/" },
        { name: "Търгове", url: window.location.origin + "/auctions" },
      ]),
    });
    return () => resetPageMeta();
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    const params = Object.fromEntries(Object.entries(filters).filter(([, v]) => v !== "" && v != null));
    const { data } = await api.get("/auctions", { params });
    setItems(data);
    setLoading(false);
  }, [filters]);

  useEffect(() => { load(); }, [load]);

  const reset = () => setFilters({ make: "", fuel: "", transmission: "", region: "", body_type: "", min_price: "", max_price: "", year_min: "", year_max: "", status: "live", sort: "ending_soon", q: "" });
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

  const Select = ({ k, label, options }) => (
    <div>
      <label className="overline text-[hsl(var(--ink-muted))] block mb-2">{label}</label>
      <select value={filters[k]} onChange={(e) => set(k, e.target.value)} className="w-full border border-[hsl(var(--line))] h-10 px-3 text-sm bg-white" data-testid={`filter-${k}`}>
        <option value="">Всички</option>
        {options.map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    </div>
  );

  const Sidebar = (
    <aside className="bg-white border border-[hsl(var(--line))] p-6 space-y-5 rounded-card">
      <div className="flex items-center justify-between">
        <h2 className="font-serif text-xl">Филтри</h2>
        <button onClick={reset} className="text-xs underline text-[hsl(var(--ink-muted))]" data-testid="reset-filters">Изчисти</button>
      </div>

      <Select k="make" label="Марка" options={mergeMakes(facets.makes)} />
      <Select k="body_type" label="Тип купе" options={facets.body_types} />
      <Select k="fuel" label="Гориво" options={facets.fuels} />
      <Select k="transmission" label="Скоростна кутия" options={facets.transmissions} />
      <Select k="region" label="Регион" options={facets.regions} />

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="overline text-[hsl(var(--ink-muted))] block mb-2">Година от</label>
          <input type="number" value={filters.year_min} onChange={(e) => set("year_min", e.target.value)} className="w-full border border-[hsl(var(--line))] h-10 px-3 text-sm" data-testid="filter-year-min" />
        </div>
        <div>
          <label className="overline text-[hsl(var(--ink-muted))] block mb-2">до</label>
          <input type="number" value={filters.year_max} onChange={(e) => set("year_max", e.target.value)} className="w-full border border-[hsl(var(--line))] h-10 px-3 text-sm" data-testid="filter-year-max" />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="overline text-[hsl(var(--ink-muted))] block mb-2">Цена от €</label>
          <input type="number" value={filters.min_price} onChange={(e) => set("min_price", e.target.value)} className="w-full border border-[hsl(var(--line))] h-10 px-3 text-sm" data-testid="filter-min-price" />
        </div>
        <div>
          <label className="overline text-[hsl(var(--ink-muted))] block mb-2">до €</label>
          <input type="number" value={filters.max_price} onChange={(e) => set("max_price", e.target.value)} className="w-full border border-[hsl(var(--line))] h-10 px-3 text-sm" data-testid="filter-max-price" />
        </div>
      </div>

      <div>
        <label className="overline text-[hsl(var(--ink-muted))] block mb-2">Статус</label>
        <div className="grid grid-cols-3 border border-[hsl(var(--line))] rounded-md overflow-hidden">
          {[
            { v: "live", l: "Активни" },
            { v: "ended", l: "Приключили" },
            { v: "sold", l: "Продадени" },
          ].map((o) => (
            <button
              key={o.v}
              onClick={() => set("status", filters.status === o.v ? "" : o.v)}
              className={`text-xs py-2 border-r last:border-r-0 border-[hsl(var(--line))] ${filters.status === o.v ? "bg-[hsl(var(--ink))] text-white" : ""}`}
              data-testid={`filter-status-${o.v}`}
            >{o.l}</button>
          ))}
        </div>
      </div>
    </aside>
  );

  return (
    <main className="rule-b" data-testid="auctions-page">
      <div className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-10 py-12">
        <div className="overline text-[hsl(var(--accent))]">Търгове</div>
        <h1 className="font-serif text-4xl lg:text-5xl tracking-tight mt-3">Разгледайте обявите</h1>

        <div className="mt-6 max-w-2xl relative">
          <Search size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-[hsl(var(--ink-muted))]" />
          <input
            type="text"
            value={filters.q}
            onChange={(e) => set("q", e.target.value)}
            placeholder="Търси марка, модел, цвят, описание…"
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
            {items.length} резултата{filters.q && <> за „<span className="text-[hsl(var(--ink))]">{filters.q}</span>"</>}
            {saveMsg && <span className="ml-3 text-[hsl(var(--accent))] inline-flex items-center gap-1"><Check size={13} /> {saveMsg}</span>}
            {saveErr && <span className="ml-3 text-[hsl(var(--danger))]">{saveErr}</span>}
          </p>
          <div className="flex items-center gap-2 sm:gap-3 w-full sm:w-auto">
            <button onClick={saveSearch} className="btn btn-secondary !py-2 !px-3 sm:!px-4 flex items-center gap-1.5 text-xs sm:text-sm shrink-0" data-testid="save-search-btn">
              <BookmarkPlus size={14} />
              <span className="hidden sm:inline">Запази търсенето</span>
              <span className="sm:hidden">Запази</span>
            </button>
            <select value={filters.sort} onChange={(e) => set("sort", e.target.value)} className="flex-1 sm:flex-none border border-[hsl(var(--line))] h-10 px-2 sm:px-3 text-xs sm:text-sm bg-white min-w-0" data-testid="sort-select">
              <option value="ending_soon">Завършващи</option>
              <option value="newest">Най-нови</option>
              <option value="price_asc">Цена ↑</option>
              <option value="price_desc">Цена ↓</option>
              <option value="most_bids">Най-много</option>
            </select>
            <button onClick={() => setOpen(true)} className="lg:hidden btn btn-secondary !py-2 !px-3 sm:!px-4 flex items-center gap-1.5 text-xs sm:text-sm shrink-0" data-testid="open-filters">
              <SlidersHorizontal size={14} />
              <span className="hidden sm:inline">Филтри</span>
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
          <div className="hidden lg:block lg:col-span-3">{Sidebar}</div>

          <div className="lg:col-span-9">
            {loading ? (
              <div className="py-20 text-center text-[hsl(var(--ink-muted))]">Зареждане…</div>
            ) : items.length === 0 ? (
              <div className="py-20 text-center rounded-card border border-[hsl(var(--line))]">
                <p className="font-serif text-2xl">Няма резултати</p>
                <p className="text-sm text-[hsl(var(--ink-muted))] mt-2">Опитайте с други думи или изчистете филтрите.</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-6 stagger" data-testid="auctions-grid">
                {items.map((a) => <AuctionCard key={a.id} auction={a} />)}
              </div>
            )}
          </div>
        </div>
      </div>

      {open && (
        <div className="fixed inset-0 z-50 bg-black/40 lg:hidden" onClick={() => setOpen(false)}>
          <div className="absolute inset-y-0 right-0 w-[88vw] max-w-sm bg-white overflow-auto" onClick={(e) => e.stopPropagation()}>
            <div className="p-4 flex items-center justify-between rule-b">
              <span className="font-serif text-xl">Филтри</span>
              <button onClick={() => setOpen(false)}><X /></button>
            </div>
            <div className="p-4">{Sidebar}</div>
          </div>
        </div>
      )}
    </main>
  );
}
