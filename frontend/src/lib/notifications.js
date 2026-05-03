/** Resolve a notification's localized title/body.
 *
 * Notifications stored after 2026-04-27 carry `type` + `data`. We render
 * them via i18n keys `notifications.types.{type}.{title|body}` with
 * `data` interpolated. Older notifications fall back to the stored
 * literal `title`/`body`.
 *
 * Safety: we ALWAYS prefer the literal stored `title`/`body` when
 * present — that guarantees a user never sees a blank notification row
 * even if we added a new `type` on the backend without shipping an i18n
 * entry for it. The i18n lookup is used only when the stored fields are
 * empty (the normal case for typed notifications).
 */
export function resolveNotification(n, t) {
  if (!n) return { title: "", body: "" };
  const literalTitle = (n.title || "").trim();
  const literalBody = (n.body || "").trim();
  if (literalTitle || literalBody) {
    return { title: literalTitle, body: literalBody };
  }
  if (n.type) {
    const tr = t(`notifications.types.${n.type}.title`, { defaultValue: "", ...(n.data || {}) });
    const br = t(`notifications.types.${n.type}.body`, { defaultValue: "", ...(n.data || {}) });
    if (tr || br) return { title: tr, body: br };
    // Final fallback: humanise the type itself so the row is never blank
    const humanised = n.type.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
    return { title: humanised, body: "" };
  }
  return { title: "", body: "" };
}

