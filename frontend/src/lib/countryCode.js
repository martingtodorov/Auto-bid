/**
 * European Vehicle Registration Codes (commonly seen on number plates as
 * an oval country sticker). The codes are NOT ISO 3166-1 alpha-2 — they
 * predate ISO and a handful of them differ (e.g. Germany is `D`, not
 * `DE`; France is `F`, not `FR`; Italy is `I`, not `IT`). We use them
 * verbatim because that's what a European driver expects to see.
 *
 * Source: UNECE Distinguishing Signs of Vehicles in International Traffic.
 *
 * The map is intentionally inclusive: both English names and a few common
 * native-language synonyms (e.g. "България") so a listing imported from
 * mobile.bg / autoscout24 doesn't drop through the cracks.
 *
 * Returns the raw input verbatim for anything we don't recognise — better
 * than rendering an empty badge.
 */
const COUNTRY_TO_CODE = {
  // ── EU + Balkans + Eastern Europe ────────────────────────────────────
  albania: "AL",
  andorra: "AND",
  austria: "A",
  belarus: "BY",
  belgium: "B",
  "bosnia and herzegovina": "BIH",
  bosnia: "BIH",
  bulgaria: "BG",
  българия: "BG",
  croatia: "HR",
  cyprus: "CY",
  "czech republic": "CZ",
  czechia: "CZ",
  denmark: "DK",
  estonia: "EST",
  finland: "FIN",
  france: "F",
  germany: "D",
  deutschland: "D",
  greece: "GR",
  hungary: "H",
  iceland: "IS",
  ireland: "IRL",
  italy: "I",
  italia: "I",
  kosovo: "RKS",
  latvia: "LV",
  liechtenstein: "FL",
  lithuania: "LT",
  luxembourg: "L",
  malta: "M",
  moldova: "MD",
  monaco: "MC",
  montenegro: "MNE",
  netherlands: "NL",
  "north macedonia": "NMK",
  macedonia: "NMK",
  norway: "N",
  poland: "PL",
  portugal: "P",
  romania: "RO",
  românia: "RO",
  russia: "RUS",
  "san marino": "RSM",
  serbia: "SRB",
  slovakia: "SK",
  slovenia: "SLO",
  spain: "E",
  españa: "E",
  sweden: "S",
  switzerland: "CH",
  schweiz: "CH",
  turkey: "TR",
  türkiye: "TR",
  ukraine: "UA",
  "united kingdom": "GB",
  uk: "GB",
  "great britain": "GB",
  vatican: "V",
};

/**
 * Convert a free-text country name into a 1-3 letter vehicle registration
 * code. Case-insensitive, trims whitespace, and treats already-short
 * inputs (2-3 chars, all caps) as already-coded — passes through.
 *
 * Examples:
 *   countryCode("Bulgaria")  → "BG"
 *   countryCode("Germany")   → "D"
 *   countryCode("DE")        → "DE"   (looks like ISO code, passthrough)
 *   countryCode("D")         → "D"    (already a registration code)
 *   countryCode("")          → ""
 */
export function countryCode(input) {
  const raw = (input ?? "").trim();
  if (!raw) return "";
  // Passthrough: already a short code (1-3 chars, all alphabetic uppercase).
  if (raw.length <= 3 && /^[A-Z]+$/.test(raw)) return raw;
  const hit = COUNTRY_TO_CODE[raw.toLowerCase()];
  return hit || raw;
}
