import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Trophy, TrendingUp, MessageSquare, Gavel, BadgeCheck } from "lucide-react";

import { api, formatEUR } from "../lib/apiClient";
import { setPageMeta, resetPageMeta } from "../lib/seo";

const TABS = [
  { key: "reputation", Icon: Trophy, labelKey: "leaderboard.tab_reputation", labelDefault: "Репутация" },
  { key: "sellers",    Icon: TrendingUp, labelKey: "leaderboard.tab_sellers",    labelDefault: "Продажби" },
  { key: "commenters", Icon: MessageSquare, labelKey: "leaderboard.tab_commenters", labelDefault: "Коментари" },
  { key: "bidders",    Icon: Gavel, labelKey: "leaderboard.tab_bidders",    labelDefault: "Наддавания" },
];

/**
 * Community leaderboard.
 *
 * Four tabs (reputation / sellers / commenters / bidders) × two time
 * ranges (all-time / last 30 days) → eight possible result sets, each
 * cached by the API for 60s. The frontend memoises by (tab, period) too
 * so switching back and forth is instant.
 */
export default function LeaderboardPage() {
  const { t } = useTranslation();
  const [tab, setTab] = useState("reputation");
  const [period, setPeriod] = useState("all");
  const [cache, setCache] = useState({});      // { `${tab}:${period}`: rows[] }
  const [loading, setLoading] = useState(true);
  const key = `${tab}:${period}`;
  const rows = cache[key];

  useEffect(() => {
    setPageMeta({
      title: t("leaderboard.meta_title", "Класация · Auto&Bid"),
      description: t(
        "leaderboard.meta_desc",
        "Най-активните продавачи, коментатори и наддавачи в Auto&Bid.",
      ),
    });
    return () => resetPageMeta();
  }, [t]);

  useEffect(() => {
    if (cache[key]) { setLoading(false); return; }
    setLoading(true);
    let cancelled = false;
    api.get("/leaderboard", { params: { type: tab, period, limit: 20 } })
      .then((r) => {
        if (cancelled) return;
        setCache((c) => ({ ...c, [key]: r.data || [] }));
        setLoading(false);
      })
      .catch(() => !cancelled && setLoading(false));
    return () => { cancelled = true; };
  }, [key, tab, period, cache]);

  // Metric column label + formatter depends on the active tab. Kept in
  // a single switch so adding a new tab stays a one-file change.
  const renderMetric = (r) => {
    if (tab === "sellers")     return t("leaderboard.metric_sold", "{{n}} продажби", { n: r.metric });
    if (tab === "commenters")  return t("leaderboard.metric_karma", "+{{n}} карма", { n: r.metric });
    if (tab === "bidders")     return t("leaderboard.metric_bids", "{{n}} бида", { n: r.metric });
    return t("leaderboard.metric_reputation", "{{n}} точки", { n: r.metric });
  };

  const renderExtra = (r) => {
    if (tab === "sellers" && r.extra?.total_eur)
      return <span className="text-xs text-[hsl(var(--ink-muted))]">· {formatEUR(r.extra.total_eur)}</span>;
    if (tab === "bidders" && r.extra?.total_eur)
      return <span className="text-xs text-[hsl(var(--ink-muted))]">· {formatEUR(r.extra.total_eur)} общо</span>;
    if (tab === "commenters" && r.extra?.comments)
      return <span className="text-xs text-[hsl(var(--ink-muted))]">· {r.extra.comments} коментара</span>;
    if (tab === "reputation" && r.extra)
      return (
        <span className="text-xs text-[hsl(var(--ink-muted))]">
          · {r.extra.sold || 0} продажби · +{r.extra.karma || 0} карма · {r.extra.bids || 0} бида
        </span>
      );
    return null;
  };

  return (
    <div className="max-w-5xl mx-auto px-4 py-10" data-testid="leaderboard-page">
      <div className="mb-8">
        <h1 className="font-serif text-4xl lg:text-5xl tracking-tight">
          {t("leaderboard.title", "Класация")}
        </h1>
        <p className="mt-2 text-[hsl(var(--ink-muted))]">
          {t("leaderboard.subtitle", "Най-активните членове на Auto&Bid общността.")}
        </p>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-2 flex-wrap border-b border-[hsl(var(--line))] pb-3 mb-4">
        {TABS.map(({ key: k, Icon, labelKey, labelDefault }) => (
          <button
            key={k}
            onClick={() => setTab(k)}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-semibold transition ${
              tab === k
                ? "bg-[hsl(var(--accent))] text-white"
                : "text-[hsl(var(--ink-muted))] hover:bg-[hsl(var(--surface))]"
            }`}
            data-testid={`leaderboard-tab-${k}`}
          >
            <Icon size={14} /> {t(labelKey, labelDefault)}
          </button>
        ))}
        <div className="flex-1" />
        {/* Period toggle */}
        <div className="inline-flex rounded-full border border-[hsl(var(--line))] p-0.5 text-sm">
          {["all", "month"].map((p) => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={`px-3 py-1 rounded-full transition ${
                period === p
                  ? "bg-[hsl(var(--ink))] text-[hsl(var(--bg))]"
                  : "text-[hsl(var(--ink-muted))]"
              }`}
              data-testid={`leaderboard-period-${p}`}
            >
              {p === "all" ? t("leaderboard.all_time", "Всички времена") : t("leaderboard.month", "30 дни")}
            </button>
          ))}
        </div>
      </div>

      {/* Rows */}
      {loading ? (
        <div className="py-20 text-center text-[hsl(var(--ink-muted))]">
          {t("common.loading", "Зареждам…")}
        </div>
      ) : !rows?.length ? (
        <div className="py-20 text-center text-[hsl(var(--ink-muted))]">
          {t("leaderboard.empty", "Все още няма данни за тази категория.")}
        </div>
      ) : (
        <div className="divide-y divide-[hsl(var(--line))] border border-[hsl(var(--line))] rounded-2xl overflow-hidden">
          {rows.map((r) => {
            const linkTo = r.dealer_slug ? `/${r.dealer_slug}` : `/profile/${r.user_id}`;
            return (
              <Link
                key={r.user_id}
                to={linkTo}
                className="flex items-center gap-4 px-4 py-3 hover:bg-[hsl(var(--surface))]/60 transition"
                data-testid={`leaderboard-row-${r.rank}`}
              >
                <span
                  className={`w-8 text-center font-bold tabular-nums ${
                    r.rank === 1 ? "text-yellow-500 text-lg"
                      : r.rank === 2 ? "text-gray-400"
                        : r.rank === 3 ? "text-amber-700"
                          : "text-[hsl(var(--ink-muted))]"
                  }`}
                >
                  {r.rank}
                </span>
                <div className="w-10 h-10 rounded-full bg-[hsl(var(--surface))] border border-[hsl(var(--line))] overflow-hidden flex items-center justify-center shrink-0">
                  {r.avatar_url
                    ? <img src={r.avatar_url} alt={r.name} className="w-full h-full object-cover" />
                    : <span className="font-serif text-sm text-[hsl(var(--ink-muted))]">{r.name?.[0] || "?"}</span>}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className="font-semibold truncate">{r.name}</span>
                    {r.is_verified_dealer && (
                      <BadgeCheck size={14} className="text-[hsl(var(--accent))] shrink-0" />
                    )}
                  </div>
                  <div className="text-sm text-[hsl(var(--ink-muted))]">
                    {renderMetric(r)} {renderExtra(r)}
                  </div>
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
