# Auto&Bid — Security audit (26 April 2026)

Scope: live preview backend (FastAPI / Mongo + Postgres) + React SPA.
Method: code review + black-box probes via REACT_APP_BACKEND_URL.

---

## 🚨 CRITICAL — fixed during this audit

### F-1. TOTP secret leak via PATCH /api/me/profile  *(CVSS ≈ 7.5, fixed)*
**Before:** `PATCH /api/me/profile` returned the full Mongo user document with only `password_hash` excluded. Any holder of the user’s JWT could read the user’s plaintext `totp_secret`, generating valid 2FA codes forever — full 2FA bypass.

**Repro:**
```
curl -X PATCH /api/me/profile  -H "Authorization: Bearer <token>" -d '{}'
→ { ..., "totp_secret":"MMHJRAHT2TXESR4ZHXRX5TAAK6YKFAHR", ... }
```
**Fix:** added `totp_secret` and `totp_backup_codes` to the projection in `server.py:1892`. Verified ✅.

### F-2. TOTP secrets returned by admin user-list & user-detail endpoints  *(fixed)*
`GET /api/admin/users` and `GET /api/admin/users/{id}` returned every user’s `totp_secret` to admins/moderators. Any compromised admin or moderator could harvest all 2FA secrets and impersonate users.

**Fix:** projection extended in `routers/admin.py:264, 269`.

---

## 🟡 MEDIUM — recommended

### M-1. CORS wide-open (`Access-Control-Allow-Origin: *`)
`backend/.env` has `CORS_ORIGINS="*"`. Browsers will refuse credentials with wildcard, but any non-credentialed call from any origin is allowed. Restrict to:
```
CORS_ORIGINS="https://autoandbid.com,https://autoandbid.bg,https://autoandbid.ro,https://*.preview.emergentagent.com"
```

### M-2. Outdated `react-router-dom` (7.11.0)
`yarn audit` lists 2 high + 1 moderate advisories patched in **7.12.0**:
- High: open-redirect XSS
- High: SSR XSS in `ScrollRestoration`
- Mod: CSRF in Server Actions

We don’t use SSR/Server Actions, so real impact is low — still bump:
```
yarn add react-router-dom@^7.12.0
```

### M-3. Dev-time advisories from `react-scripts` & `eslint`
~140 advisories total but they live inside `react-scripts` (build tool), `eslint` (lint) and `jest` (tests) — none ship to production bundles. Tracked, no immediate action.

### M-4. Image payload not bounded
`AuctionCreate.images` accepts an unlimited list of base64 strings. A logged-in user can post a draft with hundreds of MB of images → DoS / Mongo 16 MB doc limit. Mitigation: cap server-side total payload size and per-image bytes (e.g., 8 MB / image, 60 images max).

### M-5. CSP allows `'unsafe-inline'` and `'unsafe-eval'` for scripts
Required by current React setup but means a stored-XSS bug elsewhere is far more dangerous. Path forward: move to nonce-based CSP after CRA → Vite migration.

### M-6. `dangerouslySetInnerHTML` on CMS hero headline
`LandingPage.jsx:69` injects raw `cmsHeadline` markup. Currently only an admin (super-admin) can set it via `PUT /admin/settings`, but a single XSS through the admin account becomes an account-takeover vector for every visitor.
Mitigation: sanitize through DOMPurify before injection, or only allow the explicit `<em>` tag and replace newline with `<br/>`.

---

## ✅ Already strong

| Area | Status |
|---|---|
| Password hashing | bcrypt, default 12 rounds. Verified bypass-resistant. |
| JWT `alg=none` bypass | Rejected (`HS256` enforced). |
| Authentication on admin endpoints | `GET/PUT/DELETE /api/admin/*` all return 401 without Bearer token. |
| Rate limiting (slowapi) | Login 10/min, register 5/min, forgot-password 5/min, /reset 5/min. Tested → triggers 429 on attempt #9. |
| Login enumeration | Identical "Грешен имейл или парола" for both unknown email and bad password. |
| Mass-assignment | `PATCH /me/profile` only updates `phone` and `sms_opt_in`; attempts to set `role` / `is_verified_dealer` / `id` / `email` are silently ignored. |
| NoSQL injection on search | `q` parameter wrapped with `re.escape()` before `$regex`. |
| Lite-WAF middleware | Blocks `<script>`, `javascript:`, `OR 1=1`, `'; drop table` etc. with 400. |
| Security headers | HSTS, CSP, X-Frame-Options=SAMEORIGIN, X-Content-Type-Options=nosniff, Referrer-Policy=strict-origin-when-cross-origin, Permissions-Policy=geolocation/mic/cam=()  |
| Forgot-password | bcrypt-hashed 6-digit OTP, 15 min TTL, max 5 verification attempts, anti-enumeration response. |
| GDPR self-erasure | `DELETE /api/auth/me` cascades + anonymizes listings. |
| Public profile (`/api/users/{id}/profile`) | Server explicitly composes a slim DTO: `id`, `name`, `role`, `member_since` only — no PII leak. |
| Auction detail | No VIN, password_hash, seller email/phone returned to public callers. |
| Admin Stripe secrets | Stored in `site_settings`, masked in GET via `mask_secret`, never returned in clear. |
| Mongo auctions sort/filter | All user input cast to typed Pydantic models — no operator injection. |
| 2FA challenge | Server stores SHA-256 hashed challenge token; secret never leaves backend except after explicit `/2fa/enable` (one-time provisioning). |

---

## Action items
1. **DONE** F-1, F-2 (TOTP leak).
2. **TODO** M-1 — switch `CORS_ORIGINS` in production env.
3. **TODO** M-2 — `yarn upgrade react-router-dom@^7.12.0`.
4. **TODO** M-4 — add max body size middleware + per-image size guard in `AuctionCreate`.
5. **NICE** M-6 — sanitize `cmsHeadline` (DOMPurify).
6. **LATER** M-5 — adopt nonce-based CSP after build-tool migration.
