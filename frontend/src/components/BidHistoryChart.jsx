import React, { useEffect, useState, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceDot, CartesianGrid } from "recharts";
import { api, formatEUR, intlLocale } from "../lib/apiClient";

/**
 * Public bid history chart.
 *
 * Plots the price-over-time curve for an auction. Anchored at the
 * auction's starting bid (chart's left edge) and steps up at every
 * placed bid. Marks anti-snipe-triggered bids with an accent dot.
 *
 * Reads from /api/auctions/{id}/bid-history (Postgres-backed, ACID).
 */
export default function BidHistoryChart({ auctionId, currentBidEur, refreshKey }) {
  const { i18n, t } = useTranslation();
  const [history, setHistory] = useState([]);
  const [startingBid, setStartingBid] = useState(null);
  const [startsAt, setStartsAt] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api
      .get(`/auctions/${auctionId}/bid-history`)
      .then((r) => {
        if (cancelled) return;
        setHistory(r.data.history || []);
        setStartingBid(r.data.starting_bid_eur ?? 0);
        setStartsAt(r.data.starts_at);
      })
      .catch(() => {})
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [auctionId, refreshKey, currentBidEur]);

  const data = useMemo(() => {
    const points = [];
    if (startingBid != null) {
      points.push({
        ts: startsAt ? new Date(startsAt).getTime() : Date.now() - 1000 * 60 * 60 * 24,
        amount: startingBid,
        label: t("auction.chart_start"),
        isStart: true,
      });
    }
    history.forEach((h) => {
      points.push({
        ts: new Date(h.created_at).getTime(),
        amount: h.amount_eur,
        label: h.user_name,
        triggered_extension: h.triggered_extension,
      });
    });
    return points;
  }, [history, startingBid, startsAt, t]);

  if (loading || history.length === 0) return null;

  const fmtTime = (ts) => {
    try {
      return new Intl.DateTimeFormat(intlLocale(i18n.language), {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      }).format(new Date(ts));
    } catch {
      return "";
    }
  };

  return (
    <div
      className="rounded-card border border-[hsl(var(--line))] p-4 sm:p-6 bg-[hsl(var(--bg-elev))]"
      data-testid="bid-history-chart"
    >
      <div className="flex items-end justify-between flex-wrap gap-2 mb-4">
        <div>
          <div className="overline text-[hsl(var(--accent))]">{t("auction.chart_overline")}</div>
          <div className="text-sm text-[hsl(var(--ink-muted))] mt-1">
            {history.length} {history.length === 1 ? t("auction.chart_bid_singular") : t("auction.chart_bid_plural")}
          </div>
        </div>
        <div className="text-right">
          <div className="text-xs text-[hsl(var(--ink-muted))]">{t("auction.chart_growth")}</div>
          <div className="font-mono text-sm text-[hsl(var(--accent))]">
            {startingBid > 0
              ? `+${Math.round(((data[data.length - 1].amount - startingBid) / startingBid) * 100)}%`
              : "—"}
          </div>
        </div>
      </div>

      <div style={{ width: "100%", height: 240 }}>
        <ResponsiveContainer>
          <LineChart data={data} margin={{ top: 12, right: 16, left: 0, bottom: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--line))" vertical={false} />
            <XAxis
              dataKey="ts"
              type="number"
              domain={["dataMin", "dataMax"]}
              tickFormatter={fmtTime}
              tick={{ fontSize: 11, fill: "hsl(var(--ink-muted))" }}
              stroke="hsl(var(--line))"
            />
            <YAxis
              tickFormatter={(v) => `€${(v / 1000).toFixed(0)}k`}
              tick={{ fontSize: 11, fill: "hsl(var(--ink-muted))" }}
              stroke="hsl(var(--line))"
              width={56}
            />
            <Tooltip
              contentStyle={{
                background: "hsl(var(--bg))",
                border: "1px solid hsl(var(--line))",
                borderRadius: 6,
                fontSize: 12,
              }}
              labelFormatter={fmtTime}
              formatter={(v, _n, p) => [
                formatEUR(v),
                p.payload.isStart ? t("auction.chart_start") : p.payload.label,
              ]}
            />
            <Line
              type="stepAfter"
              dataKey="amount"
              stroke="hsl(var(--accent))"
              strokeWidth={2}
              dot={{ r: 3, fill: "hsl(var(--accent))", strokeWidth: 0 }}
              activeDot={{ r: 5 }}
              isAnimationActive={false}
            />
            {data
              .filter((p) => p.triggered_extension)
              .map((p, i) => (
                <ReferenceDot
                  key={`ext-${i}`}
                  x={p.ts}
                  y={p.amount}
                  r={6}
                  fill="hsl(var(--danger))"
                  stroke="hsl(var(--bg))"
                  strokeWidth={2}
                  ifOverflow="extendDomain"
                />
              ))}
          </LineChart>
        </ResponsiveContainer>
      </div>

      {data.some((p) => p.triggered_extension) && (
        <div className="text-xs text-[hsl(var(--ink-muted))] mt-3 flex items-center gap-2">
          <span className="inline-block w-2 h-2 rounded-full bg-[hsl(var(--danger))]" />
          {t("auction.chart_extension_legend")}
        </div>
      )}
    </div>
  );
}
