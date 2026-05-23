// Helper to update document meta tags dynamically (client-side)
// Social media crawlers (FB, Twitter) may not execute JS — use /api/share/{id} for public sharing links.

// --- Schema.org enum mapping (Cyrillic → canonical English) -----------------
// Google's Rich Results validator rejects Cyrillic enum strings for
// schema.org Vehicle properties. We map to the canonical English values
// it expects; unknown inputs fall through unchanged.
const _SCHEMA_ENUM = {
  body_type: {
    "Седан": "Sedan", "Хечбек": "Hatchback", "Хетчбек": "Hatchback",
    "Купе": "Coupe", "Кабрио": "Convertible", "Кабриолет": "Convertible",
    "Комби": "Estate", "Джип": "SUV", "Офроуд": "Off-road",
    "Ван": "Van", "Миниван": "Minivan", "Пикап": "Pickup",
    "Лимузина": "Limousine", "Родстер": "Roadster",
  },
  fuel: {
    "Бензин": "Petrol", "Дизел": "Diesel", "Хибрид": "Hybrid",
    "Хибриден": "Hybrid", "Plug-in хибрид": "Plug-in hybrid",
    "Електричество": "Electric", "Електрически": "Electric",
    "Газ/Бензин": "LPG/Petrol", "LPG": "LPG", "Метан": "CNG",
    "Водороден": "Hydrogen",
  },
  transmission: {
    "Автоматик": "Automatic", "Автоматична": "Automatic",
    "Ръчна": "Manual", "Полуавтоматична": "Semi-automatic",
    "Tiptronic": "Tiptronic", "Робот": "Automated", "Вариатор": "CVT",
  },
  color: {
    "Бял": "White", "Черен": "Black", "Сив": "Grey", "Сребрист": "Silver",
    "Червен": "Red", "Син": "Blue", "Зелен": "Green", "Жълт": "Yellow",
    "Оранжев": "Orange", "Кафяв": "Brown", "Бежов": "Beige",
    "Златист": "Gold", "Графит": "Graphite",
    "Тъмно син": "Dark blue", "Тъмно сив": "Dark grey",
  },
};

const schemaEnum = (kind, v) => {
  if (!v || typeof v !== "string") return v;
  return (_SCHEMA_ENUM[kind] && _SCHEMA_ENUM[kind][v]) || v;
};

const ensureMeta = (selector, attr, value) => {
  let el = document.head.querySelector(selector);
  if (!el) {
    el = document.createElement("meta");
    const [attrName, attrVal] = selector.replace("meta[", "").replace("]", "").split("=");
    el.setAttribute(attrName, attrVal.replace(/"/g, ""));
    document.head.appendChild(el);
  }
  el.setAttribute(attr, value);
};

const ensureLink = (rel, href, extra = {}) => {
  const hrefLang = extra.hreflang;
  const sel = hrefLang ? `link[rel="${rel}"][hreflang="${hrefLang}"]` : `link[rel="${rel}"]`;
  let el = document.head.querySelector(sel);
  if (!el) {
    el = document.createElement("link");
    el.setAttribute("rel", rel);
    Object.entries(extra).forEach(([k, v]) => el.setAttribute(k, v));
    document.head.appendChild(el);
  }
  el.setAttribute("href", href);
};

const DEFAULT = {
  title: "Auto&Bid.bg — Онлайн търгове за автомобили",
  description:
    "Auto&Bid.bg — най-добрите автомобили на търг. Прозрачно наддаване, редакционен преглед, 60+ снимки и защита на купувача.",
  image: `${window.location.origin}/og-default.jpg`,
  url: window.location.origin,
};

export function setPageMeta({ title, description, image, url, jsonLd, robots, locale, alternates } = {}) {
  const t = title || DEFAULT.title;
  const d = (description || DEFAULT.description).slice(0, 300);
  const img = image || DEFAULT.image;
  const u = url || window.location.href;

  document.title = t;
  // `<html lang>` mirrors the i18n decision (locale "bg|en|ro") so
  // screen readers and Google's content-language signal stay in sync.
  if (locale) {
    document.documentElement.setAttribute("lang", locale);
  }

  ensureMeta('meta[name="description"]', "content", d);
  // Respect the global deindex override if it's in place — its meta element
  // is marked with `data-global="1"` and must win over per-page robots.
  const deindex = document.getElementById("deindex-robots");
  if (!deindex) {
    ensureMeta('meta[name="robots"]', "content", robots || "index, follow, max-image-preview:large, max-snippet:-1");
  }

  ensureMeta('meta[property="og:title"]', "content", t);
  ensureMeta('meta[property="og:description"]', "content", d);
  ensureMeta('meta[property="og:image"]', "content", img);
  ensureMeta('meta[property="og:url"]', "content", u);
  ensureMeta('meta[property="og:type"]', "content", title && title !== DEFAULT.title ? "article" : "website");
  if (locale) {
    const ogLocale = { bg: "bg_BG", en: "en_US", ro: "ro_RO" }[locale] || "bg_BG";
    ensureMeta('meta[property="og:locale"]', "content", ogLocale);
  }

  ensureMeta('meta[name="twitter:card"]', "content", "summary_large_image");
  ensureMeta('meta[name="twitter:title"]', "content", t);
  ensureMeta('meta[name="twitter:description"]', "content", d);
  ensureMeta('meta[name="twitter:image"]', "content", img);

  ensureLink("canonical", u);

  // ---- hreflang alternates ----
  // `alternates` is `{ bg: "https://...", en: "...", ro: "..." }`. We
  // strip any existing dynamic alternate links first to avoid stale
  // entries piling up across navigations, then emit one per language
  // + an `x-default` row pointing at the English (canonical) edition.
  document.head.querySelectorAll('link[rel="alternate"][data-dynamic="1"]').forEach((n) => n.remove());
  if (alternates && typeof alternates === "object") {
    Object.entries(alternates).forEach(([code, href]) => {
      if (!href) return;
      const link = document.createElement("link");
      link.rel = "alternate";
      link.hreflang = code;
      link.href = href;
      link.setAttribute("data-dynamic", "1");
      document.head.appendChild(link);
    });
    if (alternates.en) {
      const xd = document.createElement("link");
      xd.rel = "alternate";
      xd.hreflang = "x-default";
      xd.href = alternates.en;
      xd.setAttribute("data-dynamic", "1");
      document.head.appendChild(xd);
    }
  }

  // Optional structured data (JSON-LD)
  const id = "dynamic-jsonld";
  const existing = document.getElementById(id);
  if (existing) existing.remove();
  if (jsonLd) {
    const s = document.createElement("script");
    s.type = "application/ld+json";
    s.id = id;
    s.text = typeof jsonLd === "string" ? jsonLd : JSON.stringify(jsonLd);
    document.head.appendChild(s);
  }
}

export function resetPageMeta() {
  setPageMeta(DEFAULT);
  const existing = document.getElementById("dynamic-jsonld");
  if (existing) existing.remove();
}

// Build schema.org Vehicle JSON-LD for an auction detail page.
// Vehicle IS-A Product in schema.org's hierarchy — so the Offer block must
// carry the full Merchant listings payload (price, currency, availability,
// shipping, return policy) to qualify for the rich SERP card.
//
// Auction-state → schema.org availability:
//   live / reserve_not_met (active) → InStock
//   sold                            → SoldOut
//   ended / withdrawn               → Discontinued
//   pending review                  → PreOrder
export function buildVehicleJsonLd(a, url) {
  if (!a) return null;

  // --- Price: prefer current_bid_eur, fall back to starting_bid_eur --------
  const priceValue = Number(a.current_bid_eur ?? a.starting_bid_eur ?? 0);
  const hasPrice = Number.isFinite(priceValue) && priceValue > 0;

  // --- Seller block (Organization fallback to Auto&Bid marketplace) --------
  const seller = a.seller_name
    ? { "@type": "Person", name: a.seller_name }
    : { "@type": "Organization", name: "Auto&Bid", url: window.location.origin };

  // --- Availability mapping ---------------------------------------------
  // Required for Google "Merchant listings" rich results. Without it the
  // SERP card silently falls back to the plain blue link.
  let availability = "https://schema.org/InStock";
  if (a.status === "sold") availability = "https://schema.org/SoldOut";
  else if (["ended", "withdrawn", "cancelled"].includes(a.status)) availability = "https://schema.org/Discontinued";
  else if (["pending", "draft"].includes(a.status)) availability = "https://schema.org/PreOrder";

  // --- Shipping details (Bulgaria / EU pickup) --------------------------
  // The platform doesn't arrange shipping itself — the buyer collects from
  // the seller's city. We surface that as `0.00 EUR` shipping rate (free
  // pickup) covering EU so the rich result shows "Free pickup" instead of
  // "No shipping info". Country code falls back to BG if not stored.
  const shippingCountry = (a.country_code || "BG").slice(0, 2).toUpperCase();
  const shippingDetails = {
    "@type": "OfferShippingDetails",
    shippingRate: {
      "@type": "MonetaryAmount",
      value: 0,
      currency: "EUR",
    },
    shippingDestination: {
      "@type": "DefinedRegion",
      addressCountry: shippingCountry,
    },
    deliveryTime: {
      "@type": "ShippingDeliveryTime",
      handlingTime: { "@type": "QuantitativeValue", minValue: 0, maxValue: 3, unitCode: "DAY" },
      transitTime: { "@type": "QuantitativeValue", minValue: 1, maxValue: 14, unitCode: "DAY" },
    },
  };

  // --- Return policy (auction sales are final) --------------------------
  // Per Bulgarian/EU consumer law, vehicle auction purchases between
  // private parties are NOT subject to the 14-day distance-selling return
  // right. We declare this explicitly so Google doesn't flag the listing
  // as missing return info.
  const returnPolicy = {
    "@type": "MerchantReturnPolicy",
    applicableCountry: shippingCountry,
    returnPolicyCategory: "https://schema.org/MerchantReturnNotPermitted",
  };

  // --- Offer with Rich Price, availability, shipping, returns -----------
  const offer = {
    "@type": "Offer",
    priceCurrency: "EUR",
    price: hasPrice ? priceValue : undefined,
    url,
    itemCondition: "https://schema.org/UsedCondition",
    availability,
    seller,
    shippingDetails,
    hasMerchantReturnPolicy: returnPolicy,
  };
  // priceValidUntil:
  //  - LIVE auction → `ends_at`
  //  - SOLD / ENDED → finalized_at + 30 days (snippet stays fresh
  //    post-sale instead of going stale on the close timestamp).
  if (["sold", "ended", "reserve_not_met"].includes(a.status) && a.finalized_at) {
    try {
      const fin = new Date(a.finalized_at);
      fin.setDate(fin.getDate() + 30);
      offer.priceValidUntil = fin.toISOString();
    } catch {
      if (a.ends_at) offer.priceValidUntil = a.ends_at;
    }
  } else if (a.ends_at) {
    offer.priceValidUntil = a.ends_at;
  }
  if (a.reserve_eur && !a.no_reserve) {
    // Expose reserve as a PriceSpecification range hint (min = current, max = reserve)
    offer.priceSpecification = {
      "@type": "PriceSpecification",
      priceCurrency: "EUR",
      price: hasPrice ? priceValue : a.reserve_eur,
      minPrice: hasPrice ? priceValue : a.starting_bid_eur,
      valueAddedTaxIncluded: a.vat_status === "vat_inclusive",
    };
  }
  Object.keys(offer).forEach((k) => offer[k] === undefined && delete offer[k]);

  // --- Vehicle core ---------------------------------------------------------
  const data = {
    "@context": "https://schema.org",
    "@type": "Vehicle",
    name: a.title,
    brand: a.make ? { "@type": "Brand", name: a.make } : undefined,
    model: a.model,
    manufacturer: a.make ? { "@type": "Organization", name: a.make } : undefined,
    vehicleModelDate: a.year,
    modelDate: a.year,
    productionDate: a.year ? `${a.year}` : undefined,
    bodyType: schemaEnum("body_type", a.body_type),
    fuelType: schemaEnum("fuel", a.fuel),
    vehicleTransmission: schemaEnum("transmission", a.transmission),
    color: schemaEnum("color", a.color),
    image: (a.images || []).slice(0, 6),
    description: (a.description || "").slice(0, 600),
    url,
    offers: offer,
  };

  // VIN умишлено НЕ се включва в публичния JSON-LD (privacy).

  // Mileage
  if (a.mileage_km) {
    data.mileageFromOdometer = { "@type": "QuantitativeValue", value: a.mileage_km, unitCode: "KMT" };
  }

  // Engine / Power
  if (a.engine_cc) {
    data.vehicleEngine = {
      "@type": "EngineSpecification",
      engineDisplacement: { "@type": "QuantitativeValue", value: a.engine_cc, unitCode: "CMQ" },
    };
    if (a.power_hp) {
      data.vehicleEngine.enginePower = { "@type": "QuantitativeValue", value: a.power_hp, unitCode: "BHP" };
    }
  }

  // Number of doors / drive config when known
  if (a.doors) data.numberOfDoors = a.doors;
  if (a.drive_type) data.driveWheelConfiguration = a.drive_type;

  // AggregateRating — buyer-to-seller reviews surface as star ratings in
  // Google SERP. Only emit when there are ≥ 1 reviews; an empty review
  // count triggers a structured-data warning in Search Console.
  const ratingCount = Number(a.seller_rating_count || 0);
  const ratingAvg = Number(a.seller_rating_avg || 0);
  if (ratingCount > 0 && ratingAvg > 0) {
    data.aggregateRating = {
      "@type": "AggregateRating",
      ratingValue: ratingAvg,
      reviewCount: ratingCount,
      bestRating: 5,
      worstRating: 1,
    };
  }

  // Clean top-level undefined
  Object.keys(data).forEach((k) => data[k] === undefined && delete data[k]);
  return data;
}

// Build a BreadcrumbList JSON-LD block. items is [{name, url}, ...] in order from root to leaf.
export function buildBreadcrumbs(items) {
  if (!items || !items.length) return null;
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: items.map((it, i) => ({
      "@type": "ListItem",
      position: i + 1,
      name: it.name,
      item: it.url,
    })),
  };
}

// Build a FAQPage JSON-LD block from [{q, a}, ...]
export function buildFaqJsonLd(qa) {
  if (!qa || !qa.length) return null;
  return {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: qa.map((it) => ({
      "@type": "Question",
      name: it.q,
      acceptedAnswer: {
        "@type": "Answer",
        text: it.a,
      },
    })),
  };
}

// Combine multiple JSON-LD blocks into a single array payload for the <script> tag.
export function combineJsonLd(...blocks) {
  const clean = blocks.filter(Boolean);
  if (!clean.length) return null;
  if (clean.length === 1) return clean[0];
  return { "@context": "https://schema.org", "@graph": clean };
}

// ---------------------------------------------------------------------------
// Organization + WebSite block for the homepage. Unlocks the Google
// "Sitelinks search box" on SERP when our site is authoritative for a query
// like "Auto&Bid" — Google embeds a search input directly in the listing.
//
// Spec: https://developers.google.com/search/docs/appearance/sitelinks-search-box
// ---------------------------------------------------------------------------
export function buildOrganizationAndWebSite({ name, url, logo, sameAs, searchUrl } = {}) {
  const org = {
    "@context": "https://schema.org",
    "@type": "Organization",
    name: name || "Auto&Bid",
    url,
    logo,
  };
  if (Array.isArray(sameAs) && sameAs.length) org.sameAs = sameAs;
  Object.keys(org).forEach((k) => org[k] === undefined && delete org[k]);

  const website = {
    "@context": "https://schema.org",
    "@type": "WebSite",
    name: name || "Auto&Bid",
    url,
  };
  if (searchUrl) {
    website.potentialAction = {
      "@type": "SearchAction",
      target: { "@type": "EntryPoint", urlTemplate: `${searchUrl}{search_term_string}` },
      "query-input": "required name=search_term_string",
    };
  }
  Object.keys(website).forEach((k) => website[k] === undefined && delete website[k]);
  return [org, website];
}

// ---------------------------------------------------------------------------
// ItemList of Vehicle items for /auctions and /sold-cars index pages.
//
// Google can show a "Vehicle listing" carousel in SERP when an index page
// exposes an ItemList of products/vehicles. Each ListItem points to the
// canonical auction URL — Google then crawls those individual pages for the
// rich Vehicle markup we already emit on AuctionDetailPage.
//
// `items` must be an array of auction-shaped objects with at minimum
// {id, title, slug?}; we use the same auctionUrl() resolver the cards do.
// `urlFor` is a function (auction) => absolute_url so callers can inject the
// app's own routing/locale logic without a circular import.
// ---------------------------------------------------------------------------
export function buildAuctionItemList(items, urlFor, name) {
  if (!Array.isArray(items) || !items.length) return null;
  // Cap at 30 — Google ignores anything beyond that and we keep the payload
  // small enough to inline in the page <head>.
  const capped = items.slice(0, 30);
  return {
    "@context": "https://schema.org",
    "@type": "ItemList",
    name: name || "Auctions",
    numberOfItems: capped.length,
    itemListElement: capped.map((a, i) => {
      const li = {
        "@type": "ListItem",
        position: i + 1,
        url: urlFor(a),
        name: a.title,
      };
      if (a.images && a.images[0]) li.image = a.images[0];
      return li;
    }),
  };
}

// ---------------------------------------------------------------------------
// CollectionPage wrapper for the Leaderboard. Leaderboard isn't a product
// listing so ItemList of users would be noise — instead we emit a
// CollectionPage describing the page itself + ItemList of top entries as
// `Person` items (no `Vehicle` here).
// ---------------------------------------------------------------------------
export function buildPersonRanking(items, urlFor, name) {
  if (!Array.isArray(items) || !items.length) return null;
  const capped = items.slice(0, 25);
  return {
    "@context": "https://schema.org",
    "@type": "ItemList",
    name: name || "Leaderboard",
    numberOfItems: capped.length,
    itemListElement: capped.map((u, i) => ({
      "@type": "ListItem",
      position: i + 1,
      item: {
        "@type": "Person",
        name: u.name || u.username,
        url: urlFor ? urlFor(u) : undefined,
      },
    })),
  };
}
