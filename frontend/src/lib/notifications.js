/** Resolve a notification's localized title/body.
 *
 * Notifications stored after 2026-04-27 carry `type` + `data`. We render
 * them via i18n keys `notifications.types.{type}.{title|body}` with
 * `data` interpolated. Older notifications fall back to the stored
 * literal `title`/`body`.
 */
export function resolveNotification(n, t) {
  if (!n) return { title: "", body: "" };
  const known = n.type && t(`notifications.types.${n.type}.title`, { defaultValue: "" });
  if (known) {
    return {
      title: t(`notifications.types.${n.type}.title`, n.data || {}),
      body: t(`notifications.types.${n.type}.body`, { defaultValue: "", ...(n.data || {}) }),
    };
  }
  return { title: n.title || "", body: n.body || "" };
}
