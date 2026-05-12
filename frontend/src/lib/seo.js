// Helper to update document meta tags dynamically (client-side)
// Social media crawlers (FB, Twitter) may not execute JS — use /api/share/{id} for public sharing links.

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
// Включваме само цена + валута за Rich Price snippets.  По изрично решение
// НЕ слагаме `availability` — Google не валидира статуса на търг достатъчно
// добре и това генерира “Sold out / Out of stock” warnings.
export function buildVehicleJsonLd(a, url) {
  if (!a) return null;

  // --- Price: prefer current_bid_eur, fall back to starting_bid_eur --------
  const priceValue = Number(a.current_bid_eur ?? a.starting_bid_eur ?? 0);
  const hasPrice = Number.isFinite(priceValue) && priceValue > 0;

  // --- Seller block (Organization fallback to Auto&Bid marketplace) --------
  const seller = a.seller_name
    ? { "@type": "Person", name: a.seller_name }
    : { "@type": "Organization", name: "Auto&Bid", url: window.location.origin };

  // --- Offer with Rich Price (no availability) -----------------------------
  const offer = {
    "@type": "Offer",
    priceCurrency: "EUR",
    price: hasPrice ? priceValue : undefined,
    url,
    itemCondition: "https://schema.org/UsedCondition",
    seller,
  };
  if (a.ends_at) offer.priceValidUntil = a.ends_at; // ISO timestamp -> auction end
  if (a.reserve_eur && !a.no_reserve) {
    // Expose reserve as a PriceSpecification range hint (min = current, max = reserve)
    offer.priceSpecification = {
      "@type": "PriceSpecification",
      priceCurrency: "EUR",
      price: hasPrice ? priceValue : a.reserve_eur,
      minPrice: hasPrice ? priceValue : a.starting_bid_eur,
      valueAddedTaxIncluded: a.vat_status === "vat_included",
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
    bodyType: a.body_type,
    fuelType: a.fuel,
    vehicleTransmission: a.transmission,
    color: a.color,
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
