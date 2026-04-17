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
  title: "AutoBid.bg — Онлайн търгове за автомобили в България",
  description:
    "AutoBid.bg — най-добрите автомобили на търг в България. Прозрачно наддаване, редакционен преглед, 60+ снимки и защита на купувача.",
  image: `${window.location.origin}/og-default.jpg`,
  url: window.location.origin,
};

export function setPageMeta({ title, description, image, url, jsonLd, robots } = {}) {
  const t = title || DEFAULT.title;
  const d = (description || DEFAULT.description).slice(0, 300);
  const img = image || DEFAULT.image;
  const u = url || window.location.href;

  document.title = t;

  ensureMeta('meta[name="description"]', "content", d);
  ensureMeta('meta[name="robots"]', "content", robots || "index, follow, max-image-preview:large, max-snippet:-1");

  ensureMeta('meta[property="og:title"]', "content", t);
  ensureMeta('meta[property="og:description"]', "content", d);
  ensureMeta('meta[property="og:image"]', "content", img);
  ensureMeta('meta[property="og:url"]', "content", u);
  ensureMeta('meta[property="og:type"]', "content", title && title !== DEFAULT.title ? "article" : "website");

  ensureMeta('meta[name="twitter:card"]', "content", "summary_large_image");
  ensureMeta('meta[name="twitter:title"]', "content", t);
  ensureMeta('meta[name="twitter:description"]', "content", d);
  ensureMeta('meta[name="twitter:image"]', "content", img);

  ensureLink("canonical", u);

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
export function buildVehicleJsonLd(a, url) {
  if (!a) return null;
  const data = {
    "@context": "https://schema.org",
    "@type": "Vehicle",
    name: a.title,
    brand: { "@type": "Brand", name: a.make },
    model: a.model,
    modelDate: a.year,
    bodyType: a.body_type,
    fuelType: a.fuel,
    vehicleTransmission: a.transmission,
    color: a.color,
    image: (a.images || [])[0],
    description: (a.description || "").slice(0, 600),
    url,
    offers: {
      "@type": "Offer",
      priceCurrency: "EUR",
      price: a.current_bid_eur,
      url,
      availability: a.status === "live" ? "https://schema.org/InStock" : "https://schema.org/SoldOut",
    },
  };
  if (a.mileage_km) {
    data.mileageFromOdometer = { "@type": "QuantitativeValue", value: a.mileage_km, unitCode: "KMT" };
  }
  if (a.engine_cc) {
    data.vehicleEngine = {
      "@type": "EngineSpecification",
      engineDisplacement: { "@type": "QuantitativeValue", value: a.engine_cc, unitCode: "CMQ" },
    };
    if (a.power_hp) {
      data.vehicleEngine.enginePower = { "@type": "QuantitativeValue", value: a.power_hp, unitCode: "BHP" };
    }
  }
  // Clean undefined
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
