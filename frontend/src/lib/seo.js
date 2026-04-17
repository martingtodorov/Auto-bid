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

const DEFAULT = {
  title: "AutoBid.bg — Автомобилни търгове",
  description: "AutoBid.bg е платформа за онлайн търгове на автомобили в България.",
  image: `${window.location.origin}/og-default.jpg`,
  url: window.location.origin,
};

export function setPageMeta({ title, description, image, url } = {}) {
  const t = title || DEFAULT.title;
  const d = (description || DEFAULT.description).slice(0, 300);
  const img = image || DEFAULT.image;
  const u = url || window.location.href;

  document.title = t;

  ensureMeta('meta[name="description"]', "content", d);

  ensureMeta('meta[property="og:title"]', "content", t);
  ensureMeta('meta[property="og:description"]', "content", d);
  ensureMeta('meta[property="og:image"]', "content", img);
  ensureMeta('meta[property="og:url"]', "content", u);
  ensureMeta('meta[property="og:type"]', "content", title && title !== DEFAULT.title ? "article" : "website");

  ensureMeta('meta[name="twitter:card"]', "content", "summary_large_image");
  ensureMeta('meta[name="twitter:title"]', "content", t);
  ensureMeta('meta[name="twitter:description"]', "content", d);
  ensureMeta('meta[name="twitter:image"]', "content", img);
}

export function resetPageMeta() {
  setPageMeta(DEFAULT);
}
