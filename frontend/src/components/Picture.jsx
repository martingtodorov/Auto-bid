/**
 * <Picture> — responsive multi-format image with AVIF → WebP → JPG
 * fallback. Reads the `images_variants[N]` manifest emitted by the
 * backend (see /app/backend/services/image_variants.py) and produces
 * a proper <picture> element with `srcset` for retina + responsive
 * delivery.
 *
 * Falls back gracefully:
 *   • manifest missing → renders a plain <img> with the legacy URL.
 *   • specific size missing → ignored, other sources still work.
 *
 * Usage:
 *   <Picture
 *     variant={images_variants[0]}        // backend manifest
 *     fallbackSrc={images[0]}              // legacy URL if no manifest
 *     size="card"                          // thumb | card | gallery | full
 *     alt="2019 BMW M2"
 *     priority                             // hero only — adds fetchpriority="high"
 *   />
 */
import React from "react";

/** Pick the variant URL for a given size + extension. Returns null if
 *  the variant doesn't exist (manifest came from an older auction
 *  uploaded before variant generation was enabled). */
function pick(variant, size, ext) {
  return variant?.variants?.[size]?.[ext] || null;
}

/**
 * Build a `srcset` string that offers two density steps (1x and 2x)
 * when the next-larger size is available. Lets a card-sized layout
 * upgrade to gallery-quality pixels on retina without blowing out
 * the byte budget for low-DPI screens.
 */
function buildSrcSet(variant, size, ext) {
  if (!variant) return null;
  const next = { thumb: "card", card: "gallery", gallery: "full", full: null }[size];
  const oneX = pick(variant, size, ext);
  if (!oneX) return null;
  const twoX = next ? pick(variant, next, ext) : null;
  return twoX ? `${oneX} 1x, ${twoX} 2x` : oneX;
}

export default function Picture({
  variant,
  fallbackSrc,
  size = "card",
  alt = "",
  className = "",
  priority = false,
  loading,        // override: "lazy" | "eager"
  onClick,
  onLoad,
  draggable,
  ...rest
}) {
  // No manifest at all (pre-variants auctions) — render the legacy URL.
  if (!variant) {
    if (!fallbackSrc) return null;
    return (
      <img
        src={fallbackSrc}
        alt={alt}
        className={className}
        loading={loading || (priority ? "eager" : "lazy")}
        decoding={priority ? "sync" : "async"}
        fetchpriority={priority ? "high" : undefined}
        onClick={onClick}
        onLoad={onLoad}
        draggable={draggable}
        {...rest}
      />
    );
  }

  const avifSet = buildSrcSet(variant, size, "avif");
  const webpSet = buildSrcSet(variant, size, "webp");
  const jpgSet = buildSrcSet(variant, size, "jpg");
  const jpgSrc = pick(variant, size, "jpg") || fallbackSrc;

  return (
    <picture>
      {avifSet && <source type="image/avif" srcSet={avifSet} />}
      {webpSet && <source type="image/webp" srcSet={webpSet} />}
      <img
        src={jpgSrc}
        srcSet={jpgSet || undefined}
        alt={alt}
        className={className}
        loading={loading || (priority ? "eager" : "lazy")}
        decoding={priority ? "sync" : "async"}
        fetchpriority={priority ? "high" : undefined}
        width={variant.width || undefined}
        height={variant.height || undefined}
        onClick={onClick}
        onLoad={onLoad}
        draggable={draggable}
        {...rest}
      />
    </picture>
  );
}

/**
 * Helper for adding a <link rel="preload" as="image"> hint inside React
 * Helmet for the LCP hero image of an auction detail page. Picks AVIF
 * if the user-agent supports it (cheap heuristic), otherwise falls back
 * to WebP/JPG. Browsers that don't know how to consume the imagesrcset
 * attribute simply ignore it — no harm done.
 */
export function preloadHints(variant, size = "gallery") {
  if (!variant) return [];
  const out = [];
  const avif = pick(variant, size, "avif");
  const webp = pick(variant, size, "webp");
  const jpg = pick(variant, size, "jpg");
  if (avif) out.push({ href: avif, type: "image/avif" });
  else if (webp) out.push({ href: webp, type: "image/webp" });
  else if (jpg) out.push({ href: jpg, type: "image/jpeg" });
  return out;
}
