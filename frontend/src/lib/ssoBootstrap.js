/**
 * Cross-domain SSO bootstrap.
 *
 * Browsers cannot share cookies across `.com` / `.bg` / `.ro` (they
 * are different public-suffix domains). When the user lands on
 * autoandbid.bg without a session cookie, we silently bounce them
 * via the canonical .com domain to pick up a 60 s nonce token, then
 * exchange it for a fresh .bg cookie. See `routers/sso.py` for the
 * full server-side flow.
 *
 * Wiring: called once from `App.js` on first render. No-op when:
 *   • Already authenticated locally (token cookie present),
 *   • SSO disabled (`REACT_APP_SSO_CANONICAL_ORIGIN` empty),
 *   • Currently visiting the canonical domain itself,
 *   • Already inside `/auth/sso/callback` (re-entry guard).
 */

const STORAGE_KEY = "sso_attempted_at";
const REENTRY_WINDOW_MS = 30_000; // 30 s — much longer than the 60 s
                                  // nonce TTL would invite re-loops on
                                  // failure; tighter avoids that.

/** Origin the browser should treat as canonical for SSO. Configured
 *  via env so dev/preview can opt out. Production should set this to
 *  https://autoandbid.com. */
function canonicalOrigin() {
  const v = (process.env.REACT_APP_SSO_CANONICAL_ORIGIN || "").trim().replace(/\/$/, "");
  return v;
}

/** Are we currently on the canonical origin? */
function isOnCanonical() {
  const c = canonicalOrigin();
  if (!c) return true; // SSO disabled — short-circuit so callers no-op
  return window.location.origin.replace(/\/$/, "") === c;
}

/** Heuristic: do we have a local session? We can't read HttpOnly
 *  cookies, so we check the readable CSRF cookie left next to the
 *  auth cookie at login time (see `_set_auth_cookies` in routers/auth.py). */
function hasLocalSession() {
  try {
    return document.cookie.split(";").some((c) => c.trim().startsWith("csrf_token="));
  } catch {
    return false;
  }
}

/** True iff we *just* tried an SSO redirect — prevents loops when the
 *  canonical domain replies "no session" (anonymous user). */
function recentlyAttempted() {
  try {
    const t = Number(sessionStorage.getItem(STORAGE_KEY) || "0");
    return t && Date.now() - t < REENTRY_WINDOW_MS;
  } catch {
    return false;
  }
}

function markAttempted() {
  try { sessionStorage.setItem(STORAGE_KEY, String(Date.now())); } catch { /* ignore */ }
}

export function maybeStartSsoBootstrap() {
  const canonical = canonicalOrigin();
  if (!canonical) return; // SSO disabled in this env
  if (isOnCanonical()) return; // canonical IS the source of truth
  if (window.location.pathname.startsWith("/auth/sso/")) return; // re-entry guard
  if (hasLocalSession()) return; // already logged in here
  if (recentlyAttempted()) return; // anonymous user — don't loop

  markAttempted();
  const returnTo = window.location.href;
  const url = `${canonical}/auth/sso/start?return_to=${encodeURIComponent(returnTo)}`;
  window.location.replace(url);
}
