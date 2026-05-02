// SEO-friendly auction URL builder.
//
// URLs go from `/auctions/<uuid>` to `/auctions/<slug>-<suffix>` where:
//   • `slug`   — kebab-cased auction title (ASCII-transliterated from
//                Cyrillic; safe length cap at 80 chars).
//   • `suffix` — first 8 chars of the canonical UUID. Unique enough to
//                disambiguate two listings with identical titles.
//
// Backend resolves either shape: the server-side middleware picks up the
// trailing 8-char suffix and rewrites the path to the canonical UUID
// BEFORE the router sees it (see `auction_slug_middleware` in server.py).
// That means all existing `/api/auctions/{id}/...` endpoints keep working
// unchanged, and old bookmarked UUID links still resolve.

// Lightweight Cyrillic → Latin transliteration (Bulgarian alphabet).
// We're not trying for linguistic purity — just something crawlers and
// humans can parse. The suffix guarantees uniqueness either way.
const CYR_MAP = {
  а:"a", б:"b", в:"v", г:"g", д:"d", е:"e", ж:"zh", з:"z", и:"i", й:"y",
  к:"k", л:"l", м:"m", н:"n", о:"o", п:"p", р:"r", с:"s", т:"t", у:"u",
  ф:"f", х:"h", ц:"ts", ч:"ch", ш:"sh", щ:"sht", ъ:"a", ь:"y", ю:"yu", я:"ya",
  А:"A", Б:"B", В:"V", Г:"G", Д:"D", Е:"E", Ж:"Zh", З:"Z", И:"I", Й:"Y",
  К:"K", Л:"L", М:"M", Н:"N", О:"O", П:"P", Р:"R", С:"S", Т:"T", У:"U",
  Ф:"F", Х:"H", Ц:"Ts", Ч:"Ch", Ш:"Sh", Щ:"Sht", Ъ:"A", Ь:"Y", Ю:"Yu", Я:"Ya",
};

function slugify(input) {
  if (!input) return "";
  const s = String(input);
  let out = "";
  for (const ch of s) out += CYR_MAP[ch] ?? ch;
  return out
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")      // strip combining marks
    .replace(/&/g, " and ")
    .replace(/[^a-z0-9]+/g, "-")          // non-alphanum → dash
    .replace(/^-+|-+$/g, "")
    .slice(0, 80);
}

/**
 * Build the public URL for an auction.
 * Accepts either a full auction object (`{id, title, make, model, year}`)
 * or a `{id, title}` subset. Returns `/auctions/<slug>-<suffix>`.
 *
 * Fallback: if `id` is missing, returns `/auctions/` — caller handles.
 * Fallback 2: if title is missing, returns `/auctions/<id>` unchanged.
 */
export function auctionUrl(auction) {
  if (!auction || !auction.id) return "/auctions/";
  const id = String(auction.id);
  const suffix = id.replace(/-/g, "").slice(0, 8);
  // Prefer the richest title available. Some ticker/notification payloads
  // only ship `{auction_id, auction_title}` so accept either key.
  const title = auction.title || auction.auction_title || "";
  const composed = [auction.year, auction.make, auction.model]
    .filter(Boolean)
    .join(" ");
  const base = title || composed;
  const slug = slugify(base);
  if (!slug) return `/auctions/${id}`;
  return `/auctions/${slug}-${suffix}`;
}

/** Same shape, but for pages that only know the id (no title yet). */
export function auctionUrlFromId(id) {
  if (!id) return "/auctions/";
  return `/auctions/${id}`;
}
