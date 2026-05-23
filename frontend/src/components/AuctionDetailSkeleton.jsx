import React from "react";

/**
 * Loading-state placeholder for AuctionDetailPage.
 *
 * The block dimensions mirror the real page so when the auction payload
 * resolves and the component swaps in, there's effectively zero
 * cumulative layout shift (Lighthouse CLS ≈ 0). The pulse animation
 * is a subtle 1.4s linear shimmer — visible enough to communicate
 * "loading", quiet enough not to compete with the cars below the fold.
 *
 * Visible parts (mirrors AuctionDetailPage layout exactly):
 *   - Hero photo gallery placeholder (16:9 main + 4 thumbnails)
 *   - Title + subtitle row (year · mileage · fuel · location)
 *   - Right column: bidding block (current bid + input + CTA)
 *   - Specs grid (8 mini-cards)
 *   - Description block (3 lines)
 */
const Bone = ({ className = "", style }) => (
  <div
    className={`bg-[hsl(var(--surface))] rounded-card ${className}`}
    style={style}
    aria-hidden="true"
  />
);

export default function AuctionDetailSkeleton() {
  return (
    <main className="container max-w-7xl mx-auto px-4 lg:px-8 py-8 lg:py-12 ab-skeleton" aria-busy="true" aria-live="polite">
      {/* Breadcrumbs */}
      <div className="flex items-center gap-2 mb-6">
        <Bone className="h-3 w-16" />
        <Bone className="h-3 w-20" />
        <Bone className="h-3 w-32" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 lg:gap-12">
        {/* Left column: gallery + content (8/12) */}
        <div className="lg:col-span-8 space-y-6">
          {/* Hero photo */}
          <Bone className="aspect-[16/9] w-full" />
          {/* Thumbnail row */}
          <div className="grid grid-cols-4 gap-2">
            {[0, 1, 2, 3].map((i) => (
              <Bone key={i} className="aspect-[16/10] w-full" />
            ))}
          </div>

          {/* Title + meta row */}
          <div className="space-y-3 pt-2">
            <Bone className="h-9 w-3/4" />
            <Bone className="h-4 w-1/2" />
          </div>

          {/* Specs grid */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-4">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="border border-[hsl(var(--line))] rounded-card p-3 space-y-2">
                <Bone className="h-3 w-16" />
                <Bone className="h-5 w-20" />
              </div>
            ))}
          </div>

          {/* Description */}
          <div className="space-y-3 pt-6">
            <Bone className="h-5 w-40" />
            <Bone className="h-3 w-full" />
            <Bone className="h-3 w-11/12" />
            <Bone className="h-3 w-10/12" />
            <Bone className="h-3 w-9/12" />
          </div>
        </div>

        {/* Right column: bidding block (4/12) */}
        <aside className="lg:col-span-4 space-y-5">
          <div className="border border-[hsl(var(--line))] rounded-card p-5 space-y-5">
            {/* Time-left pill */}
            <Bone className="h-6 w-24" />
            {/* Current bid */}
            <div className="space-y-2">
              <Bone className="h-3 w-20" />
              <Bone className="h-10 w-40" />
            </div>
            {/* Bid input */}
            <Bone className="h-12 w-full" />
            {/* Submit button */}
            <Bone className="h-12 w-full" />
            {/* Buyer-fee note */}
            <Bone className="h-3 w-3/4" />
          </div>
          {/* Watchlist + share row */}
          <div className="flex gap-3">
            <Bone className="h-11 flex-1" />
            <Bone className="h-11 w-11" />
          </div>
        </aside>
      </div>
    </main>
  );
}
