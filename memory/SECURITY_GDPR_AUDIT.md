# AutoBids.bg — Security & GDPR Audit

> Дата: Apr 2026
> Обхват: Phase 1–4.5 имплементации

---

## ✅ Преминава — Security

### Secret management
- **JWT_SECRET** идва от `.env`, не хардкодиран
- **Stripe secret/webhook secret** никога не се връщат в cleartext след запис; `/admin/stripe` GET показва само маска (`sk_t…7890`)
- **Emergent LLM key** не е използван в тази платформа
- Няма `logger.info`/`print` на пароли, secret-и, или webhook payload body
- Audit log никога не съхранява стойности — само полетaта

### Authentication
- bcrypt за пароли (pyotp backup codes също bcrypt)
- JWT HS256 със secret от env
- TOTP 2FA (RFC 6238, pyotp) с 8 backup кода
- Forgot password: 6-digit OTP (bcrypt hashed), 15-min TTL, max 5 опита, anti-enumeration (идентичен отговор независимо от наличие на акаунт)
- `/auth/login` login challenge flow блокира direct JWT когато 2FA е активно

### Authorization
- `require_admin` + `require_admin_or_moderator` дивергентни dependencies
- Модератор НЕ може: settings PUT, Stripe CMS, ban/delete/suspend на admin/moderator
- Права на собственост: seller update own auction; admin override всички

### Input validation
- Всички входове минават през Pydantic v2 (length caps, regex patterns)
- Stripe keys валидирани по prefix (`sk_test_`, `pk_live_`, etc.)
- VAT fields: gross > net enforced
- Make създаване: само от известния DB каталог

### NoSQL injection
- Motor driver използва dict-queries, не string templating
- Няма `$where` или `eval()` употреби
- Regex queries минават през `re.escape()` за потребителски вход

### Rate limiting (SlowAPI)
- `/auth/login`: 10/min
- `/auth/register`: 5/min
- `/auth/forgot-password`: 5/min
- `/auth/reset-password`: 5/min
- `/auth/2fa/verify`: 10/min
- `/auctions/{id}/bids`: 30/min
- `/sell` и общи POST endpoints: 10-30/min

### Security headers
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: strict-origin-when-cross-origin`
- Permissions-Policy ограничена

### Webhook
- Stripe webhook: HMAC v1 signature verification с dynamic secret
- Фалшиви подписи → 400 Invalid signature

### Maintenance mode
- 503 на всички write endpoints когато е включен
- Админ + auth остават достъпни за възстановяване

---

## ⚠️ Препоръки за бъдещи сесии

### High priority
- **Verification link за email**: в момента `/admin/users/{id}/resend-verification` изпраща напомняне без уникален токен; за реална email verification — добави `email_verification_tokens` колекция с jwt tokens 24h TTL
- **CSRF protection за cookie-based auth**: ако в бъдеще мигрираме от localStorage JWT към httpOnly cookies, нужен е SameSite=Strict + CSRF token. Сега JWT в header → CSRF няма вектор
- **Login brute force**: в момента имаме rate-limit по IP. За sophisticated attackers (proxy rotation), добави account-level lockout след N грешни опита
- **CORS production**: `allow_origins` в момента чете от env; в production .env задай конкретен origin (не `*`)
- **CAPTCHA**: register/forgot-password/bid да имат hCaptcha или Cloudflare Turnstile

### Medium priority
- **Password policy**: засега `min_length=6`. В production покачи на 8 + complexity (upper/lower/digit)
- **Audit log retention**: добави cron който изтрива audit entries по-стари от 1 година
- **Session invalidation**: JWT няма revocation list. При suspend/ban потребителят може да продължи с активен JWT до expire. Добави `jti` + Redis blacklist или check `suspended` на всеки request

### Low priority
- **2FA enforcement за admin/moderator**: силно препоръчително за production
- **IP + device fingerprint logging**: за login events (Phase 3.2 roadmap)
- **WAF rules**: SQLi/XSS pattern matching (Phase 3.3)

---

## GDPR Compliance

### ✅ Преминава
- **Right to access**: `/api/auth/me` връща всички публични данни; `/api/users/{id}/profile` публичен
- **Right to rectification**: `/api/auth/me` позволява обновяване на собствени данни
- **Right to erasure**: `DELETE /api/auth/me` каскадно изтрива:
  - bids, comments, watches, saved_searches, bidding_credits, vin_requests, reviews, user_notes
  - Обявите се анонимизират (seller_name='Изтрит потребител', seller_id='deleted') — запазени за legal ledger
  - High-bidder referrals cleared
- **Data minimization**: Public profile не излъчва phone/email; VIN се маскира за non-viewers
- **Cookie consent**: банер с Accept/Reject (localStorage), задължителен преди non-essential трекъри
- **Audit trail**: всички admin действия логнати (кой, кога, от кой IP, какво)
- **Secret storage**: bcrypt hashes, никога plaintext

### ⚠️ Препоръки за GDPR
- **Privacy Policy страница** (/privacy) — основа за банерния линк; добави legal текст
- **Data retention policy**: добави автоматично изтриване на audit_log, stripe_events, auth_challenges (>90 дни)
- **Data export**: `GET /api/auth/me/export` → JSON/ZIP с всички данни на потребителя (Right to portability)
- **DPA**: Data Processing Agreement с Resend (email), Stripe (payments), MongoDB hosting — подписани и архивирани
- **Cookie categorization**: сегашният банер е binary; добави категории (Essential/Analytics/Marketing)
- **Newsletter consent**: ако се добавят маркетинг имейли — отделно opt-in
- **Cross-border transfer**: уточни хостинг регион (MongoDB, Resend)

### Legal документи които трябва да добавите
- Privacy Policy (GDPR + Bulgarian GDPR адаптация)
- Terms of Service (вече има `terms_content` в CMS)
- Cookie Policy
- DPA с third parties
- Records of Processing Activities (член 30 GDPR)

---

## Vulnerability scan summary

| Клас | Статус | Детайли |
|------|--------|---------|
| SQL injection | N/A | MongoDB, използва dict queries |
| NoSQL injection | ✅ Защитено | Motor driver, няма `$where`/eval |
| XSS (stored) | ✅ Защитено | React auto-escape + `dangerouslySetInnerHTML` не се използва |
| XSS (reflected) | ✅ Защитено | Pydantic валидация на всички входове |
| CSRF | ✅ N/A | JWT в Authorization header, не cookies |
| Broken auth | ✅ Защитено | bcrypt + JWT + TOTP + rate-limit |
| Secret exposure | ✅ Защитено | Маскиране + audit без стойности |
| SSRF | ✅ Защитено | mobile.bg scraper има SSRF защита |
| Open redirect | ✅ Защитено | Route validation в React Router |
| Path traversal | ✅ N/A | Без file uploads на backend |
| DoS via rate | ⚠️ Средно | SlowAPI работи, но няма global ip-based fallback |
| Clickjacking | ✅ Защитено | X-Frame-Options: DENY |

---

**Заключение:** платформата в текущото си състояние няма критични уязвимости за production MVP. Main gaps за пълна enterprise-grade security са: CAPTCHA, session invalidation при ban, и legal документите за GDPR.
