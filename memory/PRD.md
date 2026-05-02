# autobids.bg — PRD (Product Requirements Document)

## Original problem statement
Създаване на landing страница и пълно функционално приложение за автомобилни аукциони (подобно на Cars and Bids / Bring a Trailer) на български език. Включва: класически/модерен дизайн, реално наддаване с база данни (FastAPI + MongoDB), потребителски профили, админ панел, WebSocket live bidding, Stripe pre-auth (2%), email/SMS нотификации (Resend, Twilio), и маскиране на VIN номера.

## User preferred language
Български

## Tech stack
- Frontend: React (CRA) + Tailwind + Shadcn
- Backend: FastAPI + Motor (Mongo async) + WebSockets
- Auth: JWT
- 3rd party: Resend (email), Twilio (SMS), Stripe (MOCKED)

## Completed work
### Earlier iterations
- Класически/модерен дизайн (Manrope + зелен акцент)
- JWT auth, register/login
- Admin seed account (admin@autobids.bg / admin123)
- WebSocket live bidding
- 2% Buyer's premium с mock Stripe pre-authorization
- Base64 качване на снимки в SellPage
- Reserve price логика + недостигнат резерв
- Post-auction counter-offers
- Публични профили (buyers/sellers)
- Resend email + Twilio SMS (FOMO в последните 5 мин)
- Глобална търсачка + saved searches
- VIN masking (последни 7 символа) + request-full-vin за наддавачи
- Мобилна навигация включваща admin линк
- Admin dashboard (Pending + Sold таб)

### Current iteration (Feb 2026)
- **Admin Full Edit**:
  - `AdminAuctionUpdate` Pydantic модел с ВСИЧКИ полета (включително status, ends_at, current_bid_eur, featured)
  - `GET /api/admin/auctions/{id}` — пълен документ за админ
  - `PUT /api/admin/auctions/{id}` — редактира всяко поле (валидира status от enum и ISO ends_at)
  - `POST /api/admin/auctions/{id}/remove` — soft delete (status=`removed`, освобождава preauths)
  - `POST /api/admin/auctions/{id}/restore` — връща към live/ended според ends_at
- **SellPage Mobile Keyboard Bug Fix**: Field компонент изнесен извън SellPage

### Apr 2026 — BaT-style bidding rework
- **Landing page**: Премахнати фалшивите статистики (14М+, 2840, 98%)
- **Всички обяви: 10 дни** (default `duration_days` на backend и frontend, DB обновена)
- **Преименувания**: "Записани търсения" → "Запазени търсения"; "Следени/Следи" → "Любими/Добави в любими"
- **Direct bidding (не proxy)**:
  - Въведената сума става видимият бид моментално
  - `_bid_step(price)` с тарифа: <1k→€50, 1-2.5k→€100, 2.5-5k→€150, 5-10k→€250, 10-20k→€500, 20-50k→€1000, 50-100k→€2000, >100k→€2500
  - Нов endpoint `GET /api/auctions/{id}/next-bid` → {step_eur, min_next_eur, buyer_fee_eur}
  - `_buyer_fee(amount)` = 5% от наддаването, min €150, max €4,000
  - Hard anti-sniping: бид в последните 2 мин → ends_at += 2 мин
- **Admin delete comments**: `DELETE /api/admin/comments/{id}` → soft delete, текстът се заменя с "Коментарът е премахнат поради неконструктивно съдържание."
- **Owner badge на коментари**: `is_owner` поле (seller_id == user_id) → показва зелен "Продавач" бадж
- **Hide reserve during live**: `reserve_met` се показва само при приключил търг (sold/ended/reserve_not_met), не докато е live. Премахнат "Резервът е достигнат" индикатор от AuctionCard.
- **Post-auction Negotiation Portal (BaT April 2025)**:
  - Нова колекция `negotiations` (auto-create при reserve_not_met)
  - State machine: awaiting_seller_opening (24h) → awaiting_buyer_response (24h) → awaiting_seller_final (24h) → accepted / declined / expired
  - Endpoints: `GET/POST /api/auctions/{id}/negotiation/opening|response|final|messages`
  - Messaging portal между buyer и seller (+ Продавач бадж)
  - При accept → auction status=sold + buyer fee applied (5% min €150 max €4k)
  - UI: `NegotiationPortal.jsx` компонент в AuctionDetailPage за reserve_not_met обяви

## Key API endpoints
- `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/auth/me`
- `GET /api/auctions` (публично — филтрира non-public за не-админ)
- `GET /api/auctions/{id}`, `POST /api/auctions`
- `POST /api/auctions/{id}/bids` (2% preauth)
- `POST /api/auctions/{id}/comments`
- `POST /api/auctions/{id}/watch`, `GET /api/me/watchlist`
- `GET/POST /api/me/saved-searches`
- `PATCH /api/me/profile`
- `GET /api/admin/pending`, `POST /api/admin/auctions/{id}/approve|reject|finalize|capture-premium`
- `GET /api/admin/auctions`, `GET /api/admin/auctions/{id}`, `PUT /api/admin/auctions/{id}` (NEW)
- `POST /api/admin/auctions/{id}/remove|restore` (NEW)
- `WebSocket /api/ws/auctions/{id}`

## DB schema (key collections)
- users: {id, email, password_hash, name, role, phone, sms_opt_in, created_at}
- auctions: {id, seller_id, title, make, model, year, mileage_km, fuel, transmission, body_type, power_hp, engine_cc, color, region, city, description, vin, images[], starting_bid_eur, reserve_eur, current_bid_eur, bid_count, high_bidder_id, high_bidder_name, created_at, ends_at, status, featured, premium_captured, removed_at}
- bids: {id, auction_id, user_id, user_name, amount_eur, created_at, preauth_id, preauth_status, preauth_amount_eur}
- comments, watches, vin_requests, saved_searches

## Backlog / Future tasks
- **P1** Реална Stripe интеграция — PaymentIntent preauth/capture на buyer fee (CMS и webhook верификация вече готови)
- **P2** Email verification link flow (resend endpoint готов, но без уникален токен)
- **P2** Session invalidation при ban/suspend (jti blacklist или per-request check)
- **P2** Canned email templates + manual admin→user messages + notification log UI
- **P2** Romanian i18n (ro.domain) — отделен subdomain + i18next или подобна система
- **P2** Sell-through rate / views-per-auction / bidders-per-auction charts в admin dashboard
- **P2** Data export (GDPR Right to portability) — `/api/auth/me/export`
- **P3** CAPTCHA на register/forgot/bid (hCaptcha или Cloudflare Turnstile)
- **P3** WAF layer + log IP/device fingerprint
- **P3** Cron job monitor UI + backup/restore endpoints

### Apr 2026 — Phase 3/4/5 Partial + Security/GDPR Audit (DONE)
Потребителят поиска всички 5 фази + одит; скопнах до най-ценните и документирах останалото.

**Phase 3 — Bid & User moderation:**
- Full bid history admin modal (`/admin/auctions/{id}/bids`) с triggered_extension flag
- Invalidate bid (с mandatory reason) — re-derive current_bid_eur + high_bidder
- Per-auction bidder block (`bid_blocks` collection) — платформен ban остава отделно
- Anti-sniping indicator: `bids.triggered_extension = true` когато бидът задейства extension
- User suspend/unsuspend (различно от ban — блокира само наддаване)
- Verify/unverify seller
- Internal notes колекция + UI
- VIN request log (`vin_requests` collection + admin GET)
- Resend verification email

**Phase 4 — Payments + CMS partial:**
- Buyer fee status endpoints (GET/PUT) — mark unpaid/paid/waived/refunded с note + audit
- Stripe event log endpoint (`/admin/stripe/events`) — вече имахме collection от webhook
- Views counter: `/api/auctions/{id}` инкрементира `views_count` на всеки GET

**Phase 5 — System safety:**
- OG image URL CMS в admin settings + preview
- Maintenance mode flag + message + middleware (503 за non-GET освен admin/auth)
- MaintenanceBanner компонент (автоматично при maintenance_mode=true)

**Security & GDPR:**
- Cookie consent banner (Accept/Reject localStorage)
- GDPR `DELETE /api/auth/me` self-erasure с каскадно изтриване и анонимизация на обяви
- DangerZone в /settings със сигурна confirm фраза „ИЗТРИЙ"
- Пълен security audit документ в `/app/memory/SECURITY_GDPR_AUDIT.md` с: secret management, auth, rate-limiting, NoSQL injection защита, CSRF/XSS/CORS статус, GDPR gap анализ

**НЕ са имплементирани (документирани в roadmap):**
- Canned emails + manual messages + notification log UI
- Romanian i18n (огромен обхват, нуждае от отделна сесия)
- Sell-through rate / conversion funnel charts
- Cron monitor UI + backup access
- Export transactions to CSV
- Admin role management UI (role PUT вече работи, липсва само tab)
- Privacy policy legal текст (field съществува в CMS, но трябва юридическа редакция)

Testing: **27/34 Phase 3/4/5 backend + 100% frontend regression = 79%+100%** (`iteration_7.json`). 7 skipped = fixture issue с променена парола на buyer акаунт, не функционални проблеми.

### Apr 2026 — Phase 2 Listing Hardening + Auction Lifecycle (DONE)

**Listing hardening:**
- **Predefined makes**: нова `makes` колекция (79 auto-seed стойности при startup), `GET /api/makes` публичен. SellPage замени свободен input със `<select>` от DB. Auto-reject на create с непозната марка.
- **Admin Makes CMS**: нов таб „Марки" (само super-admin може да добавя/трие). Азбучно групиране (A, B, C…). DELETE блокира при in-use (count > 0).
- **VAT fields**: `vat_status` = "exempt" | "vat_inclusive" + `price_net_eur` + `price_gross_eur`. Backend валидация (gross > net; задължителни при vat_inclusive). UI radio toggle + conditional inputs.
- **No-reserve flag**: `no_reserve: bool` — премахва reserve_eur, скрива „резерв не е достигнат" логика. UI checkbox в SellPage.
- **Preview before publish**: client-side modal `data-testid=sell-preview-modal` рендерира listing-а преди submit. „Потвърди и подай" подава след визуална проверка.
- **Duplicate as draft**: `POST /api/auctions/{id}/duplicate` — клонира като `pending` с `" (копие)"` суфикс, нулирани бидове/дати. Бутон в admin all-listings + достъпен за seller на собствени обяви.

**Auction lifecycle (всички admin-only с audit log):**
- `POST /admin/auctions/{id}/pause` + `/unpause` — запазва `paused_seconds_remaining` и го добавя при unpause
- `POST /admin/auctions/{id}/cancel` {reason} — mandatory reason (≥3 chars), status=cancelled
- `POST /admin/auctions/{id}/close-now` — force end; finalizer приключва в ≤60s
- `POST /admin/auctions/{id}/archive` + `/unarchive` — `is_archived` toggle, скрива от публични списъци
- `POST /admin/auctions/{id}/featured` — toggles `featured` bool
- Всички нови бутони в admin all-listings tab

**Public filter:** `/api/auctions` вече изключва `is_archived=true` и non-public статуси (pending/cancelled/paused/…) за non-admin viewer.

Testing: 29/30 Phase 2 backend + 32/35 Phase 1 regression + 100% frontend = **~97%** ✅ (`iteration_6.json`)

### Apr 2026 — Phase 1 Security & Admin (DONE)
Потребителят поиска 70+ функции в 12 категории; разделихме на фази. Phase 1 фокусира се върху security + admin foundation:

**Stripe CMS в admin:**
- GET/PUT `/api/admin/stripe` (super-admin only) — publishable, secret, webhook secret + test/live mode + enable toggle
- Secret-ите никога не се връщат в чист вид; показват се с маска (`sk_t…7890`)
- PUT валидира prefix-и (`sk_test_`, `pk_live_`, …); празно поле запазва текущата стойност
- Публичен `GET /api/stripe/public-config` → frontend Stripe.js конфиг
- `POST /api/webhooks/stripe` — HMAC v1 signature verification с динамичен webhook_secret, logs в `stripe_events`

**Moderator role:**
- Нов `require_admin_or_moderator` dependency
- Модератори: read достъп до settings/stats/users/audit, могат да модерират коментари
- Модератори НЕ могат: settings PUT, stripe CMS, ban/delete на служители
- AdminPage UI скрива Stripe и Settings tabs за модератори

**Audit log:**
- Нова колекция `audit_log` + `helpers.audit_log()` helper (non-blocking, never raises)
- `GET /api/admin/audit-log` с филтри (action/actor_id/target_id) + pagination
- UI tab „Журнал" в admin panel с таблица и филтър
- Логвани действия: settings.update, stripe.update, user.ban, comment.delete, auction.reactivate
- В log-а само field names — никога секретни стойности

**Forgot password (via Resend):**
- `POST /api/auth/forgot-password` → 6-цифрен код в DB (bcrypt hash, 15min TTL) + красив HTML email
- Анти-enumeration: еднакъв отговор за съществуващ/несъществуващ user
- `POST /api/auth/reset-password` — max 5 опита, used=true след успех
- Нова `/forgot-password` 3-step страница (email → код+нова парола → успех)

**2FA (TOTP):**
- `pyotp + qrcode` пакети инсталирани
- `POST /api/auth/2fa/enable` → secret + QR code data URL + provisioning URI
- `POST /api/auth/2fa/confirm` валидира TOTP → активира + връща 8 backup кода (bcrypt hashed в DB)
- Login с `totp_enabled=true` връща `{requires_2fa:true, challenge_token}` (не JWT)
- `POST /api/auth/2fa/verify` приема TOTP или backup code (еднократен)
- `POST /api/auth/2fa/disable` изисква TOTP
- UI: `TwoFactorSection` компонент в `/settings` — QR display, secret manual, confirm, backup codes, disable
- LoginPage 2FA challenge screen

**Reactivate sold auction:**
- `POST /api/admin/auctions/{id}/reactivate?days=N` — sold/ended/reserve_not_met/withdrawn/removed → live
- Нов `ends_at = now + days`, `finalized_at` се изчиства, bid история се запазва
- Бутон „Реактивирай" в admin sold tab

Testing: 33/35 backend + 100% frontend = 94% ✅ (`iteration_5.json`). 2 skipped = expected (webhook signature with real Stripe payload).

### Apr 2026 — Sold Price Tracker + Admin refactor (DONE)
- **Нов публичен stats endpoint**: `GET /api/stats/sold?days=30|90|365` → total_count, total_volume_eur, avg/median/min/max_price_eur, avg_mileage_km, by_make (top 10), by_body_type, by_month (12м), highest_sale.
- **Разширен `GET /api/auctions/sold`** с филтри: make, body_type, fuel, year_min/max, price_min/max, q, sort (recent/oldest/price_desc/price_asc), limit, offset. Връща `{items,total,offset,limit}` при употреба на параметри; плосък списък (backwards-compat) при празна заявка.
- **SalesPage преработена**: KPI панел с window toggle (30/90/365/all), топ марки bar chart, месечна тенденция, highest-sale spotlight, пълен filter bar (q + make + body_type + year_min + price_max + reset), сортиране, pagination.
- **SEO**: Page meta + BreadcrumbList JSON-LD за архива.
- **Admin router extraction**: `routers/admin.py` извлича CMS + users + stats маршрутите (settings GET/PUT, comments DELETE, stats, users GET list/single + PUT + ban/unban/DELETE) чрез `configure()` DI pattern. `server.py` намален от 2713 → 2489 реда.
- **Landing page UI polish**: Hero padding намален (`py-8 lg:py-6` → `py-6 lg:py-3`), headline spacing по-стегнат, hero featured image на десктоп е с `lg:aspect-[16/10]` вместо `4/3` за по-нисък профил.
- Testing: **40/40 backend + пълен frontend regression = 100%** ✅ (`iteration_4.json`)

### Apr 2026 — Buyer → Seller Review/Rating system (DONE)
- Нова колекция `reviews` — {id, seller_id, buyer_id, buyer_name, auction_id, auction_title, rating 1–5, text, created_at}
- Endpoints (нов `/app/backend/routers/reviews.py`):
  - `POST /api/users/{seller_id}/reviews` — само купувачът на `sold` обява; max един отзив на сделка
  - `GET /api/users/{seller_id}/reviews` → {items, rating:{avg,count}}
  - `GET /api/users/{seller_id}/rating` → {avg,count}
  - `GET /api/users/{seller_id}/reviews/eligible/{auction_id}` (auth) — eligible flag + reason
  - `GET /api/me/reviewable` — неоценените сделки на текущия купувач
- `/api/users/{id}/profile` вече връща `rating:{avg,count}`
- Frontend:
  - `SellerReviews.jsx` + reusable `<StarRating />` компонент (фракционни половинки)
  - Нов таб „Отзиви" на ProfilePage + rating карта в stats + pill в хедъра
  - JSON-LD `Person` + `AggregateRating` за SEO (Rich Results)
  - Интерактивна форма за оставяне на отзив (само за купувачи с неоценени сделки)
- Testing: 18/18 backend + пълна frontend Playwright сесия 100% ✅ (`iteration_3.json`)

### Apr 2026 (продължение) — Phase 6: Multi-language + Seller Self-Service + T&C Audit
- **T&C с device fingerprint audit (P0 fix)**:
  - `POST /api/auth/register` вече изисква `terms_accepted: true` (400 ако липсва)
  - При приемане записва в user doc: `terms_accepted_at`, `terms_accepted_ip`, `terms_accepted_user_agent`, `terms_accepted_language`, `terms_version`
  - Независим immutable запис в `audit_log` с `action=user.terms_accepted` (ZZLD/GDPR доказателство за съгласие)
  - Frontend `RegisterPage.jsx`: нов задължителен checkbox `[data-testid=register-terms-checkbox]` с линк към `/terms` и `/terms#privacy`; submit disabled докато чек-бокса не е маркиран
- **Hero CMS (multi-language)**:
  - 6 нови полета в `site_settings`: `hero_headline_{bg,ro,en}`, `hero_subtitle_{bg,ro,en}`
  - Editable в Admin → Настройки → „Hero текст на началната страница"
  - LandingPage.jsx използва CMS стойност за текущия език (falls back на i18n ако празно)
  - Headline поддържа `<em>` за курсив и newline за пренасяне
- **Seller Self-Service (с модераторско одобрение)** — нов router `/app/backend/routers/seller_requests.py`:
  - `POST /api/auctions/{id}/request-promotion` — заявка за промотиране (admin approve → `featured=true`)
  - `POST /api/auctions/{id}/request-text-change` — заявка за промяна на заглавие/описание (admin approve → прилага)
  - `PATCH /api/auctions/{id}/reorder-images` — пренареждане на снимки (seller only, no approval нужно; rejects add/remove)
  - `GET /api/me/seller-requests` + `DELETE /api/me/seller-requests/{id}` (cancel pending)
  - Admin: `GET /api/admin/seller-requests` + `POST /admin/seller-requests/{id}/approve|reject` с filter по status/type
  - Frontend: `SellerRequestModal.jsx` (drag-drop reorder + text edit + promote) + нов таб „Заявки" в admin
- **Admin UI разширение**:
  - Нов таб „Известия": notification log + CSV transaction export бутон
  - Нов таб „Имейл шаблони": CRUD на canned emails + „Изпрати тест" форма
  - Нов таб „Заявки": seller-requests queue с approve/reject actions
- **i18n пълно покритие**:
  - Нов `en.json` locale (пълен)
  - Разширени `bg.json` и `ro.json` (nav, hero, landing steps, forms, auth, auction, cta, footer, seller)
  - `LanguageSwitcher` показва BG/RO/EN + достъпен в Nav (desktop + mobile)
  - LandingPage + Nav + RegisterPage изцяло преведени
- **Testing**: `iteration_8.json` — Backend 28/31 passed (2 skipped fixture-related, 1 minor `/health` 404), Frontend 100% critical flows. 0 critical, 0 action items.

### Apr 2026 (продължение 2) — Multi-currency, domain-based i18n, page translations
- **Domain-based language auto-detect**: Нов custom detector в `/app/frontend/src/i18n/index.js` чете hostname и пренасочва към правилния език при първо посещение:
  - `autobids.bg` (или `REACT_APP_DOMAIN_BG`) → `bg`
  - `autobids.ro` (или `REACT_APP_DOMAIN_RO`) → `ro`
  - `autobids.com` (или `REACT_APP_DOMAIN_EN`) → `en`
  - Работи с `endsWith` така че staging/preview subdomains автоматично наследяват езика
  - Ръчният избор чрез `LanguageSwitcher` се пази в `localStorage.autobids_lang` и има приоритет
  - Redirect order: `localStorage` > `domain` > `navigator` > fallback bg
- **Multi-currency display (BGN / RON / none for EN)**:
  - Нова `formatLocal(value, lng)` функция в `apiClient.js` — връща `лв.` за bg, `lei` (RON_RATE=4.97) за ro, празно за en
  - `formatRON` exported за директна употреба
  - Call sites обновени: `AuctionCard`, `LandingPage` hero featured, `AuctionDetailPage` price column
  - BG потребители виждат EUR + лв., RO виждат EUR + lei, EN само EUR
- **Page translations (BG/RO/EN)**:
  - `LoginPage.jsx` — напълно преведена (welcome, 2FA challenge, password reset link, submit)
  - `SellPage.jsx` — hero, sub-heading, mobile.bg import box, submit/preview бутони, success screen, основни error messages
  - `AuctionDetailPage.jsx` — specs overline, "Oferte/Bids" history, comments title, current bid / sold for label, your bid label, reserve met/not met, seller, counter-offer banner, place-bid button, watchlist toggle, transmission/fuel labels
  - Нова `sell.*` namespace в трите locales; `auth.*` разширен; `auction.*` разширен с 14+ ключа
- **Hero gradient — unified with `btn-sell-gradient`**:
  - `.hero-headline em` използва същия 3-стопов зелен linear-gradient (accent → accent-ink → dark green hsl(156 72% 22%))
  - Премахнат shimmer animation — по-елегантен, статичен look
  - Enhanced drop-shadow за дълбочина
- **Fix**: duplicate `t` identifier в `AuctionDetailPage` — преименуван `[t, setT]` timer state на `[tl, setTl]`

### Apr 2026 (продължение 3) — Remaining page translations
- **Footer**: brand tagline, 3 колони (Platform/Help/Account) и 8 линка напълно преведени; copyright + "Made in Sofia" локализирани (BG по подразбиране, RO и EN варианти)
- **AuctionsPage**: hero (overline + title), search placeholder, "X results" count label, filter sidebar labels (Марка/Каросерия/Гориво/Скоростна кутия/Регион/Година от/до/Цена от/до/Всички), sort dropdown (5 опции), Save search button, empty state, loading state, mobile filter drawer title. Премахнат redundant Status toggle (live/ended/sold).
- **WatchlistPage**: overline, title, subtitle, empty state (heading + hint + CTA), loading state
- **MyListingsPage**: overline "Моят гараж", title "Мои обяви", subtitle, "Нова обява" CTA, empty state, Edit/Withdraw бутони, STATUS_META преработен да ползва `my_listings.status.*` keys; fix timer variable name collision (`t` → `tl`)
- **AdminPage**: hero overline "Администрация", title "Админ панел", всички 12 tab labels (Начало/Очакващи/Всички обяви/Заявки/Потребители/Продадени/Марки/Stripe/Известия/Имейл шаблони/Журнал/Настройки)
- Нови i18n namespaces: `footer`, `watchlist`, `auctions_page`, `my_listings` (с nested `status`), `admin` (с nested `tabs`) в трите locales
- Тествано с Playwright: RO версията на `/auctions` показва пълно преведен hero, filters, sort, footer и nav. Lei currency се показва вместо лв. Nav links и footer линкове всички преведени.

### Apr 2026 (Phase 8) — Country field + location format + "мин./min." i18n + region removal + deep detail page i18n
- **Deep translation на AuctionDetailPage**:
  - Interior figcaption (3 снимки в описанието) → `spec.interior`
  - Comment placeholder + logged-out state + submit бутон → `auction.comments_placeholder*` + `auction.comments_submit`
  - `С резерв / Без резерв` badges → `auction.with_reserve / no_reserve_badge`
  - `Водещ: {name}` → `auction.leading_bidder`
  - Related section: `Също виж / Подобни обяви / Виж всички търгове` → `auction.also_see / similar_listings / view_all_auctions`
- **PreauthModal — пълно i18n преписване**: нов `preauth.*` namespace (15 ключа) в bg/ro/en. Modal title, buyer fee label + detail, card fields, error messages, CTA, test-mode footer — всички преведени.
- **Removed `region` field**: SellPage няма повече region dropdown; AuctionsPage филтърът за регион е изтрит.
- **Filter enum verification (RO/EN)**: `Marcă/Caroserie/Combustibil/Transmisie` на RO; `Make/Body type/Fuel/Gearbox` на EN; опциите са преведени през `translateEnum` (Petrol, Automatic, SUV/Coupe/Sedan).
- **SellPage country dropdown**: Нов `country` selector (40 държави на английски, Bulgaria default).
- **Backend models**: `country: Optional[str] = "Bulgaria"` в `AuctionCreate` + optional в `AuctionUpdate`/`AdminAuctionUpdate`.
- **Data backfill**: 5 съществуващи обяви получиха `country="Bulgaria"`.
- **Location format "City, Country"**: `AuctionCard.jsx`, `AuctionDetailPage.jsx` (spec row + hero subtitle).
- **i18n — "мин." → "min." за RO/EN**: нов `common.min_short` ключ; `ImageUploader.jsx` рендерира `· min. {n}`.
- **SellPage.jsx repair**: Corrupt UTF-8 от предишна итерация е отстранен; файлът минава lint clean.
- Test: Screenshot BG/EN `/auctions` показват `Sofia, Bulgaria`; EN `/sell` показва `min. 8`; backend curl round-trip с `country: Germany` ✅.

### Apr 2026 (Phase 7) — Auto-translate + multi-lang CMS + deep UI i18n
- **Auto-translate на описания (Emergent LLM / Gemini 2.5 Flash)**:
  - Нов `/app/backend/translate.py` с `translate_text(text, target_lang)` helper
  - Endpoint `GET /api/auctions/{id}/translate-description?lang=ro|en` — превежда, кешира в DB (`description_ro`, `description_en`), връща JSON `{lang, text, cached}`
  - Rate-limit 20/min, 30s timeout, 8000 char cap
  - Translation cache се инвалидира при text-change approve
  - Frontend `DescriptionWithInteriorShots` — автоматично показва запазен превод при non-BG език, с бутон „Преведи" (и „Auto-translated" badge + „Show original" при успех)
- **Multi-language CMS pages** (`faq`/`terms`/`fees`/`contacts`/`how_it_works`):
  - Нови 15 полета в `site_settings` (`<base>_bg`, `<base>_ro`, `<base>_en`) с fallback до legacy non-suffixed field
  - Frontend helper `pickCmsContent(settings, base, lang)` с chain fallback
  - Обновени FAQPage, TermsPage, ContactsPage, FeesPage, HowItWorksPage
  - Admin UI: нов `CmsMultiLangField` компонент с BG/RO/EN тaбове за всяко от 5-те CMS полета (markdown textarea)
- **Car data translation** (фронтенд-only dictionary в `/app/frontend/src/lib/carTranslations.js`):
  - Fuels (8), transmissions (7), body types (14), colours (15), regions (27)
  - `translateEnum(value, kind, lang)` с fallback към raw stringified value
  - Wired в AuctionCard (fuel + city) и AuctionDetailPage (6 specs полета + subtitle + body_type overline)
- **Deep UI translation в AuctionDetailPage**:
  - Share button + link-copied toast
  - Verified dealer / private seller labels
  - Buyer's fee label + detail (параметризиран с pct/min/max)
  - Comment removed message (fixes stale deleted comments loaded from DB)
  - VIN number label + 3 различни masked-note варианти (anon/live/ended) + request CTA + unmasked badge
  - Bid hints (Min/step), "No bids yet", "up to credit" hint
  - Back-to-auctions link, live/connecting/offline статус pill
  - Spec labels (Year, Mileage, Engine, Power, Colour, Location, HP)
- **Deep UI translation в MyListingsPage**:
  - Reserve-not-met seller panel (accept high bid button + counter-offer form + pending counter status)
  - Promote/text-change/reorder бутони с локализирани titles
  - Status badge labels чрез `my_listings.status.*` (10 statuses)
  - Featured badge
- **Deep UI translation в AuctionCard**:
  - Sold/Ended/Urgent/Live status pills
  - Featured + Verified dealer badges
  - With-reserve / No-reserve chip
  - Current bid / Sold for label
  - Fuel + city values
- Разширени i18n файлове: `spec` namespace (7 keys), auction namespace от 33 → 54 keys, нови `private_person`, `link_copied`, `vin_*` (7 keys)
- Тестван end-to-end: EN версията на auction detail показва пълен LLM-преведен BMW M240i description (`For sale is a BMW M240i xDrive in excellent condition…`) + преведени всички specs + verified dealer + share listing. Cache работи — втора заявка е instant.

## 3rd-party integrations status
- Resend: Configured via env (RESEND_API_KEY), fallback console log
- Twilio: Configured via env (TWILIO_*), fallback console log
- Stripe: **MOCKED** (mock_pi_* tokens, 2% buyer premium simulation)

## Critical notes for future agents
- НЕ използвайте npm, само yarn
- Всички backend routes трябва да са с `/api` префикс
- `_auction_status()` е computed при четене — stored статуси: pending/rejected/withdrawn/removed/sold/reserve_not_met/ended/live
- При създаване на нови компоненти с форми: НИКОГА не дефинирайте sub-компоненти ВЪТРЕ в родителския компонент (причинява loss of focus bug)

---

## 2026-02-23 — Rich Price / Rich Snippets за SEO (DONE)
**Цел**: По-силна индексация в Google и показване на Rich Snippets (цена, наличност) за всяка страница на търг.

**Промени:**
- `/app/frontend/src/lib/seo.js` → `buildVehicleJsonLd`:
  - `offers.itemCondition` = `UsedCondition`
  - `offers.priceValidUntil` = `a.ends_at` (ISO timestamp)
  - `offers.seller` = Person (seller_name) или Organization (Auto&Bid)
  - `offers.priceSpecification` (когато има reserve_eur)
  - Properly-mapped availability: live → InStock, ended/sold → SoldOut, scheduled → PreOrder, cancelled → Discontinued
  - `vehicleIdentificationNumber` (VIN)
  - `manufacturer`, `productionDate`, `vehicleModelDate`
  - `image` e масив от до 6 снимки (не само първата)
  - Price fallback: `current_bid_eur` → `starting_bid_eur`
- `/app/backend/routers/seo.py` → `_json_ld_vehicle` (SSR за /api/share/auction/{id}):
  - Същата структура както frontend за crawlers, които не изпълняват JS

**Тест**: curl към `/api/share/auction/{id}` → валиден JSON-LD с price=24000, priceCurrency=EUR, priceValidUntil=2026-04-27, itemCondition=UsedCondition, availability=InStock, VIN=WBA2J71040VA53204. Lint passed.

## Remaining backlog (P1–P3)
- Real Stripe API keys (изчаква user keys)
- "Buy Now" за търгове (P2)
- CAPTCHA (Cloudflare Turnstile) на регистрация (P3)
- "Без резерв" badge на AuctionCard и AuctionDetailPage (P1, неначатo)
- PostgreSQL миграция: **НЕ се прави** (user decision — остава MongoDB)

## 2026-04-26 — Archive tab + AuctionsPage button polish (DONE)
- **Admin Archive tab** (`AdminArchiveTab.jsx`): list, select-all + per-row check, bulk-restore, bulk-delete (с „ИЗТРИЙ" confirm), плюс **per-row individual restore и individual delete** (всеки с собствен confirm). Wired в AdminPage под нов таб „Архив".
- **Backend route order fix**: `GET /admin/auctions/archived`, `POST /admin/auctions/bulk-restore`, `POST /admin/auctions/bulk-delete` бяха регистрирани СЛЕД `/admin/auctions/{auction_id}` → wildcard грабваше "archived" → 404. Преместени преди wildcard-а.
- **AuctionsPage UI**: Save search, Sort dropdown, Filter button — единен бял фон, `rounded-lg` (10px) border-radius (мач със search bar-а, който също получи `rounded-lg`), еднаква h-12 височина. На мобилно (`flex-1 sm:flex-none`) бутоните разпъват цялата ширина.
- i18n keys в bg/ro/en за `admin.archive.*` + `admin.tabs.archive`.

## 2026-02-23 — Hybrid PostgreSQL bidding subsystem (DONE)

**Защо**: Bid placement сега е ACID-correct → нулеви race conditions при едновременни наддавачи. Postgres се използва САМО за бидове; всичко останало (auctions, users, comments, watches, credits) остава в MongoDB.

**Нова инфраструктура:**
- PostgreSQL 15 supervisor програма (preview env) + `postgres:15-alpine` service в `docker-compose.yml`
- `POSTGRES_URL` env var в backend/.env и docker-compose
- Tables: `bids` (append-only история) + `bid_state` (per-auction state, locked via SELECT FOR UPDATE)

**Нови файлове:**
- `/app/backend/db_pg.py` — async engine + session factory (SQLAlchemy 2.0 async)
- `/app/backend/models_pg.py` — SQLAlchemy ORM (Bid, BidState)
- `/app/backend/services/bidding.py` — всички bid операции (place_bid, list_bids, has_user_bid, release_*, capture, delete_*)

**Migrated endpoints**: 
- POST `/api/auctions/{id}/bids` — място на бида с FOR UPDATE lock + min-bid revalidation вътре в транзакцията
- GET `/api/auctions/{id}/bids` 
- GET `/api/me/bids`
- POST `/api/admin/auctions/{id}/finalize`
- POST `/api/admin/auctions/{id}/capture-premium`
- POST `/api/admin/auctions/{id}/remove`
- POST `/api/admin/auctions/{id}/withdraw`
- DELETE `/api/admin/auctions/{id}` (cascade)
- GET `/api/admin/auctions/{id}/bids` + POST `/api/admin/bids/{id}/invalidate`
- GET `/api/admin/sold` (winning bid lookup)
- GET `/api/admin/stats` (count_bids)
- DELETE `/api/auth/me` + DELETE `/api/admin/users/{id}` (cascade delete bids)
- POST `/api/auctions/{id}/request-vin` (already_bid check)
- VIN reveal logic в `_assemble_auction_public`

**Sync model**: PostgreSQL = source of truth for bids. Mongo `auction.current_bid_eur`, `bid_count`, `high_bidder_*`, `ends_at` се обновяват post-commit за да продължат filter/sort/sitemap да работят без join.

**Race-condition тест**: 3 паралелни POST /bids от различни потребители със същата сума → точно един успява, останалите получават "min next bid" грешка с обновената стойност. Verified ✅

**Стара Mongo `bids` колекция**: запазена недокосната като archive (старите данни не се мигрират — само нови бидове отиват в Postgres). Index запазен.

## 2026-02-23 — Dark mode + Web Push notifications (DONE)

### Dark mode
- Three-state theme toggle (light / dark / system) в header (`/app/frontend/src/components/ThemeToggle.jsx`)
- `data-theme="dark"` атрибут на `<html>`; CSS променливи се обновяват автоматично
- Mobile address-bar tint via `<meta name="theme-color">`
- Boot-time theme apply (no flash) — `bootTheme()` в `index.js`
- Persist в `localStorage` (`ab.theme`); следва OS-level промени когато е "system"
- CSS overrides за hardcoded `bg-white`/`text-gray-*`/`border-gray-*` Tailwind classes под `html[data-theme="dark"]`
- Image `filter: brightness(0.92)` под dark theme за по-добро четене

### Web Push notifications (W3C Push API + VAPID)
**Backend:**
- `pywebpush` либ (раз b64url VAPID keys в `.env`: `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_CONTACT_EMAIL`)
- `services/push.py` — save_subscription, send_to_user (auto-prune 404/410 endpoints)
- `routers/push.py` — GET /api/push/public-key, POST /api/push/subscribe, /unsubscribe, /test
- Index: `db.push_subscriptions` (endpoint unique, user_id)
- **Triggers**: place_bid → outbid push (prev_high) + seller-got-bid push; notify_matching_saved_searches → saved-search match push

**Frontend:**
- `/public/sw.js` — service worker (push event handler + notificationclick)
- `/public/manifest.webmanifest` + 192/512 PNG icons + iOS meta tags (Add to Home Screen)
- `/src/lib/push.js` — pushAvailableHere() detection, subscribePush, unsubscribePush, sendTestPush
- `/src/components/PushSettings.jsx` — настройки с 5 състояния (loading/unsupported/ios-pwa-needed/default/denied/subscribed)
- Wired в `AccountSettingsPage.jsx`

**iOS support**: 16.4+, изисква Add to Home Screen (PWA install). UI-то показва инструкции.

**Тествано**: VAPID JWT успешно подписан, push изпратен към FCM/Mozilla endpoints, 410 responses се pruне правилно.

### Removed
- `BidHistoryChart` компонент + `/api/auctions/{id}/bid-history` endpoint + `chart_*` i18n ключове

## 2026-02-23 — Production-grade transactional outbox (DONE)

**От**: synchronous dual-write (PG → inline Mongo update)
**Към**: transactional outbox pattern с background worker

**Защо**: Ако backend крашне между PG commit и Mongo update → Mongo остава stale завинаги. Outbox решава това с **at-least-once + idempotent** доставка.

**Нови файлове:**
- `models_pg.py` → `BidEvent` table (id, auction_id, event_type, payload JSONB, applied_at, attempt_count, next_attempt_at, last_error)
- `services/outbox_worker.py` — async coroutine с 250ms poll, batch=50, exp. backoff, max_attempts=12, dead-letter

**Гаранции:**
1. **Atomic write**: `place_bid()` INSERT-ва Bid + BidEvent в **същата** PG транзакция → guaranteed consistency
2. **Sync fast path**: server.py се опитва веднага да обнови Mongo (за UX без забавяне) → ако успее, маркира event applied
3. **Worker safety net**: ако sync write fail-не (мрежа, crash), worker автоматично retry-ва с exponential backoff
4. **Idempotent writes**: Mongo update е conditional (`bid_count: {$lt: new_count}`) → replays никога не overwrite-ват по-нова държава
5. **Crash recovery**: `SELECT ... FOR UPDATE SKIP LOCKED` — worker never duplicate-processes
6. **Dead-letter**: след 12 неуспешни опита event-ът се изключва; admin може ръчно да retry-не

**Admin endpoints:**
- `GET /api/admin/bid-outbox` — health (pending count, dead_letter count, oldest pending age)
- `GET /api/admin/bid-outbox/dead-letter` — списък на dead-letter events
- `POST /api/admin/bid-outbox/{event_id}/retry` — ръчно retry

**Тествано:**
- Successful bid → event written, applied within ms, marked applied=true ✅
- Outbox health endpoint работи (admin auth) ✅
- Idempotency guard ($lt) предпазва от backwards counts ✅
- Worker boots on startup, drains pending events ✅

**Постижение**: Сега системата е безопасна срещу:
- Backend crash mid-bid
- Mongo network partition
- Concurrent bidders (FOR UPDATE lock)
- Out-of-order event delivery (idempotent guards)


---

## April 28, 2026 — Operations + UX batch

### Infrastructure: PostgreSQL persistence
- `/app/scripts/start_postgres.sh` wrapper now backs the supervisor `postgresql` program.
  - Re-installs `postgresql-15` if `/usr/lib/postgresql/15` is missing on container restart (overlay FS wipes `/usr`).
  - Persistent data dir at `/app/data/pgdata` (the `/app` mount is the only durable volume).
  - Bootstrap creates `autobid` user + `autobid_bids` database on first run, then `exec`s postgres in foreground.
- Verified by deleting `/var/lib/postgresql/15/main` then restarting supervisor: bidding tables (`bids`, `bid_state`, `bid_events`) survive.

### Sell page — gross input flow
- Starting bid, reserve and buy-now inputs now treat the entered value as **gross (incl. VAT)** when `vat_status === "vat_inclusive"`.
- Frontend converts gross → net before POST; backend storage / API contract unchanged.
- Field labels switch to "(с ДДС)" and the helper hint shows the implied **net** value ("Без ДДС {{rate}}%: {{amount}} €").

### Admin↔User two-way chat (NEW)
- **Mongo collection**: `chat_messages` `{id, thread_user_id, sender_id, sender_role, sender_name, body, created_at, read_by_user, read_by_admin}`
- **Backend** (`/app/backend/routers/chat.py`):
  - `GET /api/me/chat/messages` · `POST /api/me/chat/messages` · `POST /api/me/chat/read` · `GET /api/me/chat/unread-count`
  - `GET /api/admin/chat/threads` (aggregation grouped by user, with last message + unread count)
  - `GET /api/admin/chat/threads/{user_id}/messages` · `POST /api/admin/chat/threads/{user_id}/messages` · `POST /api/admin/chat/threads/{user_id}/read`
  - Side effects on send: admin→user fans out inbox notification + Web Push to the customer; user→admin notifies all admins/moderators in their inbox bell.
- **Frontend**:
  - `AdminChatPanel.jsx` — new "Чат" tab in Admin Panel with threads list (with unread badges + "Нов разговор" user-search) and a chat pane.
  - `UserChatPanel.jsx` — collapsible panel pinned at the top of `InboxPage` for the customer to converse with support.
- Verified end-to-end via curl (user→admin and admin→user) and screenshots of both UIs.

### Drag-to-reorder photos — touch support
- Existing desktop HTML5 drag in `SellerRequestModal` extended with **long-press touch drag** (220 ms hold, floating ghost element, drop-target highlighting).
- Up/down arrow buttons are now permanently visible on mobile (not hover-gated).
- `ImageUploader.jsx` already had cross-uploader touch drag (no change needed).

### Misc UX polish
- Mobile nav: bell icon and hamburger button grouped in a single flex container (`gap-1`) so they sit immediately next to each other instead of being pushed apart by `gap-6`.
- Admin Panel → All listings: each row now has a **Преглед** button (`Eye` icon) opening the auction detail in a new tab.
- i18n: added `forms.add` key (BG "Добави" / EN "Add" / RO "Adaugă") so the "Add photo" button in `ImageUploader` translates correctly across all locales.

### Test credentials added
- `chattest3@test.bg` / `chatpass1` — used to seed the chat thread shown in screenshots.



## Security hardening — 28 Apr 2026

### C3 — JWT в httpOnly cookie + CSRF (double-submit)
- **Backend** (`/app/backend/routers/auth.py`):
  - Помощни функции `_set_auth_cookies()` / `_clear_auth_cookies()` (`access_token` HttpOnly + `csrf_token` JS-readable, `Secure`, `SameSite=Lax`, `Max-Age=7d`).
  - `/auth/login`, `/auth/register`, `/auth/2fa/verify` записват двете cookies при успех (токенът все още се връща в body за миграционна съвместимост).
  - Нови `POST /auth/logout` (изчиства cookies) и `GET /auth/csrf` (връща/възстановява CSRF токен).
- **CSRF middleware** в `/app/backend/server.py`: за `POST/PUT/PATCH/DELETE` под `/api/*` се изисква `X-CSRF-Token` header равен на `csrf_token` cookie (timing-safe `hmac.compare_digest`). Освободени са: `/api/webhooks/*`, `/api/auth/login|register|forgot-password|reset-password|2fa/verify|csrf`, както и заявки с `Authorization: Bearer ...` (не са уязвими към CSRF).
- **Frontend**:
  - `apiClient.js` — `withCredentials: true`, axios interceptor чете `csrf_token` cookie и поставя `X-CSRF-Token` header при мутиращи методи.
  - `auth.js` — `refresh()` извиква `/auth/me` безусловно и разчита на cookies; `logout()` извиква `/auth/logout`. Стари `localStorage` токени се изчистват при login/register (миграция).
  - `LanguageSwitcher.jsx` използва `useAuth().user` вместо `localStorage.autobid_token`.

### M1 / M2 — Email enumeration prevention
- `/auth/login`: при липсващ потребител се изпълнява bcrypt срещу `_DUMMY_BCRYPT_HASH`, за да се изравни времето за отговор. Съобщенията за грешка вече са еднакви (`"Грешен имейл или парола"`).
- `/auth/forgot-password` (вече беше унифициран) — отговорът е идентичен независимо дали имейлът съществува.

### M4 — DOMPurify за CMS контент
- `LandingPage.jsx`: hero headline, който идва от настройките на сайта, се санитизира чрез `DOMPurify.sanitize()` с whitelist от `br/em/strong/span/b/i` и атрибут само `class`.
- Добавена зависимост `dompurify@^3.4.1`.

### P0 — JSON-LD без availability
- `seo.js → buildVehicleJsonLd()` повече **не** включва `offer.availability`. Запазени остават `price`, `priceCurrency`, `priceValidUntil`, `itemCondition`, `seller`, `priceSpecification` (когато има резерв).
- Решение: Google генерира некоректни "Sold out" warnings за активни търгове; цената сама по себе си е достатъчна за Rich Price snippet.

### Тест статус
- `/app/test_reports/iteration_9.json` — 15/16 backend pytest passed (1 skipped — banned user fixture), Playwright E2E flows OK.
- Тестов файл: `/app/backend/tests/test_security_c3_csrf.py`.

### Сесии (устройства) — 29 Apr 2026
- **JWT** разширен с `sid` claim → връзка към `sessions` Mongo колекция.
- **`get_current_user`** валидира session при всяка заявка; ако сесията е изтрита/изтекла → 401.  Last-seen update е rate-limited (1×/мин).
- **Парсване на User-Agent** чрез `user-agents==2.2.0`: показва модел на телефон (iPhone, Pixel 8 Pro и т.н.), browser, OS версия, IP, last-seen.
- **Endpoints**:
  - `GET /api/auth/sessions` — списък с `is_current` маркер
  - `DELETE /api/auth/sessions/{sid}` — изход от едно устройство
  - `POST /api/auth/sessions/revoke-others` — изход от всички други
  - `POST /api/auth/sessions/revoke-all` — изход от всички (включително текущото)
- **Frontend**: `SessionsSection.jsx` в Account Settings показва Smartphone/Tablet/Monitor икона, badge "Текуща сесия" + "Запомни ме", IP + relative time.
- `/auth/logout` сега и изтрива текущия session запис (не само cookies).
- Curl-проверено end-to-end: revoke от една сесия инвалидира токена на другото устройство в реално време (401).


### CMS — bug fix + Direct HTML (29 Apr 2026)
- 🐛 **Критичен бъг**: `SETTINGS_DEFAULTS` в `server.py` НЕ включваше multi-lang CMS полетата (`terms_content_bg`, `faq_content_bg` и т.н.) → Mongo пазеше стойностите, но `_load_settings_cache()` ги филтрираше при reload (защото merge само на ключове, които са в DEFAULTS).  Добавени всичките 15 markdown полета + 15 HTML полета в DEFAULTS.
- 🆕 **Direct HTML режим** за всяка от 5-те страници (Общи условия, Как работи, FAQ, Такси и комисионни, Контакти) на 3 езика → 15 нови полета `<base>_html_<lang>`.  Запис в Mongo, render през `DOMPurify` (frontend-side sanitization).
- 📐 **Render priority**: HTML > Markdown > Default React component.  Никое съществуващо съдържание не е променено — администраторите получават контрол без да губят defaults.
- 🎨 **AdminSettingsTab**: всеки CMS блок има Markdown/HTML toggle pill, badge "⚠ Активен HTML режим" когато HTML версия е попълнена за текущия език.
- 🛡️ Сигурност: `HtmlBody.jsx` използва `DOMPurify` с whitelist (h1-h6, p, a, img, table, ul/ol, blockquote, code и др.) — премахва `<script>`, on* event handlers, `javascript:` URLs, iframe, form, link, meta, style.
- ✅ Curl-проверено: PUT → GET връща стойностите; XSS опит се санитизира на render.

**Файлове**:
- Backend: `/app/backend/server.py` (DEFAULTS + public settings response), `/app/backend/models.py` (SiteSettingsUpdate +15 HTML полета)
- Frontend: `/app/frontend/src/components/HtmlBody.jsx` (нов), `/app/frontend/src/lib/settings.js` (нова `pickCmsHtml` функция), `/app/frontend/src/components/AdminSettingsTab.jsx` (CmsMultiLangField with mode toggle), `/app/frontend/src/pages/{TermsPage,FAQPage,FeesPage,HowItWorksPage,ContactsPage}.jsx`.


### Desktop +N gallery overlay & Stripe-only card capture (29 Apr 2026)

**Gallery (+N overlay)**
- Mobile (<768px) показва 5 thumbs; ако има >5, на 5-та се показва тъмен overlay `+N`.
- **Desktop (≥768px)** сега показва **10 thumbs** (2 реда от по 5); ако има >10, на 10-та се показва тъмен overlay `+N` → клик отваря lightbox от това място.
- Thumbs ≥10 → `hidden` на desktop (показани само в lightbox).
- Click handler използва `window.matchMedia("(min-width: 768px)")`, за да реши дали натискането на overlay-натия thumb отваря lightbox или просто сменя главна снимка.

**Stripe-only card capture**
- ❌ Премахнато: директно въвеждане на номер карта/CVV/exp в `PreauthModal.jsx` и `BiddingCreditModal.jsx`. UI-ите вече **никога** не пипат PAN.
- ✅ Сега: бутон "Оторизирай {amount}" в модала вика `POST /api/stripe/authorizations/create-checkout` (вече съществуващ endpoint) и `window.location.href` пренасочва към Stripe Hosted Checkout (`capture_method=manual`).
- 🔁 Post-redirect handler в `AuctionDetailPage.jsx` (`useEffect` на `?stripe_session_id=...`):
  1. Polls `GET /api/stripe/authorizations/active?auction_id=…` до 6× × 2s, докато webhook-ът не маркира hold-а като `active`.
  2. Чете `pending_credit_<auctionId>` от localStorage → регистрира credit чрез `POST /auctions/{id}/bidding-credit` с stripe `auth.id` като placeholder PM id.
  3. Чете `pending_bid_<auctionId>` от localStorage → подава бида чрез `POST /auctions/{id}/bids`.
  4. Изчиства query param-а от URL.
- ⚠️ Когато потребителят кликне Cancel в Stripe, връща се с `?stripe_cancelled=1` → показва се грешка и pending данните се изтриват.
- 🔑 За реален runtime е нужно: `STRIPE_API_KEY` (sk_live_…) и `STRIPE_WEBHOOK_SECRET` в `/app/backend/.env`. Текущо: тестов placeholder `sk_test_emergent` → endpoint връща 503 преди реалната редиректа.
- 🌍 Преводи добавени за BG/RO/EN: `preauth.stripe_secure_*`, `preauth.redirecting`, `preauth.powered_by_stripe`, `preauth.stripe_cancelled`, `preauth.stripe_pending`, `credit.redirecting`, `credit.stripe_secure_body`. Старите `card_number/cvc/validity/test_mode/err_invalid_*` ключове са оставени за backwards-compat, но не се използват от UI-а.

**Файлове:**
- `/app/frontend/src/pages/AuctionDetailPage.jsx` — gallery dual-overlay logic + post-Stripe-redirect useEffect
- `/app/frontend/src/components/PreauthModal.jsx` — пълен rewrite (Stripe redirect)
- `/app/frontend/src/components/BiddingCreditModal.jsx` — премахнато card input, Stripe redirect
- `/app/frontend/src/i18n/locales/{bg,en,ro}.json` — нови ключове



### UI Polish Animations & Copy Update (30 Apr 2026)

**Анимации (Framer-like с pure CSS keyframes):**
- 🎛️ **Мобилен филтър панел** (`/app/frontend/src/pages/AuctionsPage.jsx`):
  - Slide-in (`slideInRight` 260ms cubic-bezier(0.22,1,0.36,1)) при отваряне
  - Slide-out (`slideOutRight` 240ms cubic-bezier(0.4,0,1,1)) при затваряне
  - Backdrop `fadeIn`/`fadeOut` синхронизирано
  - `closing` state + 240ms setTimeout преди unmount
- 📱 **Мобилно hamburger меню** (`/app/frontend/src/components/Nav.jsx`):
  - `mobileMenuOpen` 280ms при отваряне (max-height + opacity)
  - `mobileMenuClose` 240ms при затваряне
  - Само на mobile (`md:hidden`)
- 🔔 **Notification panel** (`/app/frontend/src/components/NotificationBell.jsx`):
  - `dropdownIn` 180ms (opacity + translateY + scale) от `origin-top-right`
  - `dropdownOut` 160ms
  - Работи и на desktop и mobile
- Всички keyframes в `/app/frontend/src/index.css`
- `prefers-reduced-motion: reduce` спира всички


### Profile Avatars + Live Ticker Fix (30 Apr 2026)

**Profile pictures:**
- Нов компонент `Avatar.jsx` — кръгла снимка с fallback initials (детерминистични цветове).
- Нова секция `AvatarSection.jsx` в `/settings` — upload през file input → base64 → POST `/api/me/avatar`.
- Backend: `imgproc.optimize_avatar_data_url()` (256×256 center-crop, JPEG q=88, max 6MB).
- Storage: ползва `storage.store_image` (inline или S3 според `STORAGE_BACKEND`).
- При upload: backfill на `seller_avatar_url` в auctions и `user_avatar_url` в comments чрез `update_many`.
- Аватара се показва в:
  - `AuctionDetailPage.jsx` → seller card (sidebar, 44px)
  - `CommentItem` → до името на автора (28px)
- DELETE `/api/me/avatar` премахва snapshot-а от user, auctions и comments.
- Преводи: `avatar.*` ключове в bg/en/ro.

**Live ticker (`/api/auctions/featured`):**
- Махнат дублиран `{a.make}` префикс (показваше „BMW BMW M-performance").
- До 10 елемента: всички `featured && live`, после допълнено с `live && !featured` (sorted ends_at asc).

**Файлове:**
- Нови: `/app/frontend/src/components/Avatar.jsx`, `/app/frontend/src/components/AvatarSection.jsx`
- Променени: `/app/backend/server.py` (avatar endpoints, seller_avatar_url at create, user_avatar_url at comment), `/app/backend/services/image_processing.py` (optimize_avatar_data_url), `/app/frontend/src/pages/AccountSettingsPage.jsx`, `/app/frontend/src/pages/AuctionDetailPage.jsx`, `/app/frontend/src/components/LiveTicker.jsx`, i18n files.


**Copy update:**
- `bg.brand_tagline` промяна: „Първата редакционна платформа за автомобилни търгове в България..." → „Редакционна платформа за автомобилни търгове. Подбрани екземпляри, прозрачни продажби."


### Email Verification at Registration (30 Apr 2026)

**Backend (`/app/backend/routers/auth.py`):**
- `POST /api/auth/register` сега маркира новите акаунти с `email_verified: False` + `verification_required: True` и автоматично издава verification email.
- Нова `email_verifications` колекция с TTL index (`expireAfterSeconds=172800` = 48h на `created_at`).
- HMAC-SHA256 хеш на token с `JWT_SECRET` като ключ — само хешът се пише в DB, raw token-ът е само в email-а. Token: `secrets.token_urlsafe(32)` → 256 bits ентропия.
- `POST /api/auth/verify-email {token}` — атомарно консумира токен с `find_one_and_delete`. TTL freshness check (datetime aware/naive normalization).
- `POST /api/auth/resend-verification` — auth-required, 60s cooldown per user + 3/hour rate limit per IP. Изтрива стари не-консумирани токени преди да издаде нов.
- Нова dependency `require_verified_email()` (`server.py`): пропуска ако `not user.verification_required` (legacy акаунти преди 30 Apr 2026 минават) или ако `user.email_verified=True`. Иначе HTTP 403.
- Приложена на: `POST /api/auctions` (sell), `POST /api/auctions/{id}/bidding-credit`, `POST /api/auctions/{id}/bids`, `POST /api/auctions/{id}/buy-now`, `POST /api/auctions/{id}/comments`.
- Email body локализиран по `user.lang` (bg/en/ro), използва съществуваща Resend инфраструктура през `emails.send_email` + `emails._shell()` template.

**Frontend:**
- Нова страница `/verify-email?token=...` (`pages/VerifyEmailPage.jsx`) — POST към API, показва loading/success/error и refresh-ва auth state на success.
- Нов компонент `VerifyEmailBanner.jsx` (вграден в App.js след `MaintenanceBanner`) — показва се само ако `user.verification_required && !user.email_verified`. Бутон "Изпрати отново" вика `/api/auth/resend-verification`.
- Нови преводи: `verify_email.*` и `verify_banner.*` в bg/en/ro.

**Existing accounts:** не са променени (по решение на потребителя — почти всички са негови). Те нямат `verification_required` flag → require_verified_email ги пропуска.

**Тествани сценарии (30 Apr 2026, через curl + Playwright):**
- ✅ Регистрация → `email_verified=False, verification_required=True`
- ✅ POST `/auctions/.../bids` без verification → 403 „Моля, потвърдете имейл адреса си..."
- ✅ Email mock log показва правилен subject + HTML
- ✅ POST `/auth/verify-email` с валиден HMAC token → 200 + user.email_verified=True
- ✅ Frontend `/verify-email` без token → показва "Invalid link" / "No token in the link"




### Granular Notification Preferences + 2 New Events (30 Apr 2026)

**Backend (`/app/backend/services/notif_prefs.py` + integrations):**
- Нов модул `notif_prefs.py`:
  - `is_enabled(user, channel, kind)` — default-enabled при липсваща pref.
  - `normalize_input(payload)` — sanitize PATCH payload, drop unknowns, coerce bool.
  - 5 kinds × 2 channels = 10 toggle-а: `outbid`, `seller_new_bid`, `saved_search`, `ending_soon`, `reserve_met`.
- `ProfileUpdate` модел приема `notification_prefs` (partial merge през dotted-path keys в Mongo).
- Всички съществуващи notif call sites обвити с `_nprefs.is_enabled` checks.

**Нови events:**
- **`reserve_met`**: при поставен бид, ако `amount >= reserve` и още не е изпратено, маркира `reserve_met_notified=true` атомарно, праща email + push до seller-а.
- **`ending_soon`** (≈1h преди край): нов `_ending_soon_loop` background task (всеки 5 мин), стартиран при startup. Намира live търгове в прозорец 55–65 мин напред, маркира идемпотентно, праща email + push до watchers ∪ active bidders.

**Frontend:**
- Нов `NotificationToggles.jsx` (channel-agnostic switch UI с PATCH /me/profile partial + revert on failure).
- Refactor `PushSettings.jsx`: постоянен iOS install tip + granular toggles (disabled докато не е subscribed → hint).
- Нов `EmailSettings.jsx` (email channel мирор).
- Двата поставени **веднага след `AvatarSection`** в `AccountSettingsPage` (2-колонен grid).
- Преводи `notif_prefs.kinds.*`, `email_prefs.*`, `push.ios_install_tip` за bg/en/ro.

**Файлове:**
- Нови: `services/notif_prefs.py`, `components/NotificationToggles.jsx`, `components/EmailSettings.jsx`
- Променени: `server.py` (5 notif call sites + ending-soon loop + reserve-met + profile PATCH), `models.py` (ProfileUpdate.notification_prefs), `emails.py`, `services/push_templates.py`, `components/PushSettings.jsx`, `pages/AccountSettingsPage.jsx`, всички i18n.

**E2E тествано:**
- ✅ PATCH /me/profile с `{notification_prefs: {push:{outbid:false}, email:{ending_soon:false}}}` → persists в Mongo.
- ✅ Refetch /auth/me връща правилните prefs.
- ✅ Playwright UI рендер: 5 push toggles + 5 email toggles, hint "Enable push first" видим, iOS install tip визуализиран на всеки.



### Reset Timer + Unsold Tab (30 Apr 2026)

**Backend:**
- **`POST /api/admin/auctions/{id}/reset-timer`** — приема `hours` (0.5–720) или `days` (1–60). Работи само за `live`/`paused`. Изтрива `ending_soon_notified` flag за да се изпрати нов 1h reminder. Връща `{ok:true, ends_at:...}`.
- **`GET /api/admin/unsold`** — връща финализирани обяви с статус ∈ {`ended`, `reserve_not_met`, `cancelled`, `withdrawn`} и `is_archived ≠ true`. Enrich-ва high bidder email за reserve_not_met cases.

**Frontend:**
- Нов tab **„Непродадени"** (между Sold и Архивирани).
- Нов `AdminUnsoldTab.jsx`: status pill filters с counts, per-row actions (Поднови / Преглед / Редактирай / Бидове / Архив), mailto link към high bidder.
- Нов **„Reset таймер"** бутон в All Listings tab за live/paused — prompt за часове или `d:N` за дни.

**E2E тествано:**
- ✅ `POST /reset-timer?hours=24` → ends_at обновен, BMW M240i показа „23H 58M" в публичните listings.
- ✅ `GET /unsold` → 200, правилен list.
- ✅ Двата endpoint защитени с `require_admin`.

### Password Security Hardening (30 Apr 2026)

**Backend (`/app/backend/services/password_security.py`):**
- **Argon2id** като primary hashing (BSD-3, безплатен, OWASP recommendation):
  - `hash_password()` ползва `argon2-cffi` defaults (memory=46_336 KiB, time=1, parallelism=1).
  - `verify_password()` поддържа и Argon2id (`$argon2…`) и legacy bcrypt (`$2b$…`).
  - `needs_rehash()` връща `True` за всички bcrypt hashes → opportunistic migration на следващ login.
- **Complexity validation** (`validate_complexity`):
  - Минимум 8 символа (max 128).
  - Поне 1 главна буква.
  - Поне 1 цифра ИЛИ специален символ.
- **HaveIBeenPwned check** (`is_password_pwned`):
  - K-anonymity: само първите 5 chars от SHA-1 се изпращат до `api.pwnedpasswords.com/range/{prefix}`.
  - Privacy-preserving (никаква PII не пътува).
  - Безплатен, без API key.
  - Network failure → returns False (не блокира registration).
- **Per-account lockout** (`routers/auth.py`):
  - 10 неуспешни attempts → 15 мин lock на акаунта.
  - Counter `failed_login_attempts` се resetва при успешен login.
  - При login: проверка на `login_locked_until`; ако lock е активен → HTTP 429 с „Опитайте след N минути".
  - На успешен login: opportunistic rehash на bcrypt → Argon2id, изтриване на lock fields.
- Password reset endpoint също прилага complexity + HIBP проверките.
- `UserRegister.password` Field min_length вдигнат от 6 → 8.

**Frontend:**
- Нов компонент `PasswordStrengthHint.jsx` — live визуализация на 3 правила (✓/✗) под password field.
- `RegisterPage.jsx` ползва hint-а; `minLength={6}` → `minLength={8}`.
- Нов `TwoFactorPromptBanner.jsx` — показва се на email-verified users без 2FA. localStorage dismissal `abm:2fa-prompt-dismissed`. CTA → `/settings`.
- Поставен в `App.js` веднага след `VerifyEmailBanner`.
- Преводи `auth.pw_rule_*` и `twofa_prompt.*` за bg/en/ro.

**E2E тествано:**
- ✅ Парола < 8 символа → 422 (Pydantic validation)
- ✅ Без uppercase → 400 „поне една главна буква"
- ✅ Без digit/symbol → 400 „поне една цифра или специален символ"
- ✅ HIBP pwned (`Password123`) → 400 „Тази парола е била открита в публични пробиви"
- ✅ Силна парола → регистрация успешна, hash е Argon2id
- ✅ 10 неуспешни → акаунтът locked
- ✅ 11-ти опит (с правилна парола) → HTTP 429 „Опитайте след 13 минути"
- ✅ Frontend hint показва ✓/✗ live при typing

**Passkeys (WebAuthn) statused:**
- НЕ е имплементиран в тази сесия. Препоръчвам отделна сесия (4–6 часа) за пълен flow: device registration, attestation, fallback при загубен device, multi-device sync.

**Файлове:**
- Нови: `services/password_security.py`, `components/PasswordStrengthHint.jsx`, `components/TwoFactorPromptBanner.jsx`
- Променени: `server.py` (delegate hash/verify към password_security), `routers/auth.py` (register/login/reset с complexity+HIBP+lockout), `models.py` (min_length 6→8), `App.js`, `RegisterPage.jsx`, всички i18n.
- Dependency: `argon2-cffi==25.1.0` в requirements.txt.





### Hetzner Deployment Files (30 Apr 2026)

Създадена е пълна `deploy/hetzner/` структура (no Docker — nginx + systemd + uvicorn):

**`/app/deploy/hetzner/`:**
- `README.md` — арх. диаграма, prerequisites, init deploy, redeploy, Cloudflare config, rollback.
- `nginx/autoandbid.conf` — reverse proxy, SPA fallback, /api → ab-back1:8001, WebSocket support, Cloudflare real-IP, security headers.
- `systemd/autobids-backend.service` — uvicorn под `www-data`, `EnvironmentFile=/etc/autobids/backend.env`, security hardening.
- `env-templates/backend.env.example` — всички production env vars.
- `env-templates/frontend.env.production.example` — `REACT_APP_BACKEND_URL=https://autoandbid.com`.

**Ansible (`/app/deploy/hetzner/ansible/`):**
- `inventory.ini` — ab-front1 (public) + ab-back1 (private чрез ProxyJump).
- `requirements.yml` — community.general + ansible.posix.
- `group_vars/all.yml` — версии, paths, /etc/hosts mappings, private CIDR.
- 3 роли: `common/` (UFW, fail2ban, /etc/hosts), `backend/` (Python 3.11 + Mongo 7 + Postgres 16 + venv + systemd + nightly backups), `frontend/` (Node 20 + yarn build + nginx).
- 4 playbooks (всички минават `--syntax-check`): `bootstrap.yml`, `site.yml`, `deploy_backend.yml` (с rollback snapshot + health check), `deploy_frontend.yml` (atomic swap).

**Network setup (по спецификацията на хостинга):**

### High-Value Preauth Unlocks Full VIN Access (30 Apr 2026)

**Backend (`/app/backend/server.py`):**
- Нова константа `HIGH_VALUE_PREAUTH_EUR = 10000`
- Нов helper `_has_high_value_preauth(user_id)` — single MongoDB lookup на `bidding_credits` с `status: "authorized"` + `max_amount_eur: $gt 10000`
- `_public_auction()` приема нов kw-only параметър `unmask_vin: bool = False` — bypass-ва маскирането на VIN
- В `list_auctions` се прави **една** проверка per-request → подава се на всички items (no N+1)
- В `get_auction` (detail) добавена като 4-ти privilege check (admin → seller → bidder-on-this-auction → high-value-preauth)

**E2E тествано:**
- ✅ Преди инжектиране на preauth: `WBS2J71040******* masked: True`
- ✅ След инжектиране на €25k authorized: `WBS2J71040VA53204 masked: False` (както в list, така и в detail)
- ✅ След cleanup: автоматично се връща masked status

**Бизнес логика:**
- Praktically: всеки сериозен купувач който е поставил >€10k preauth на каквато и да е обява получава пълен VIN достъп до **всички** активни листинги — спестява обикалянето между обявите за инспектиране
- Threshold е strict `>` 10000 (по описанието на потребителя „anything over 10000 eur")



### Multi-Domain Setup (autoandbid.com / .bg / .ro) — 30 Apr 2026

**Frontend (вече беше готов в `/app/frontend/src/i18n/index.js`):**
- `LANG_DOMAINS = { bg: 'autoandbid.bg', ro: 'autoandbid.ro', en: 'autoandbid.com' }`
- `DomainDetector` чете `window.location.hostname` и автоматично избира език при всяко зареждане
- Detection order: `localStorage > domain > navigator > fallback(bg)`
- `LanguageSwitcher` пише в localStorage — manual override запазен per-origin

**Deployment files обновени:**
- `nginx/autoandbid.conf`:
  - Един `server` блок за всички 3 домейна (`server_name autoandbid.com autoandbid.bg autoandbid.ro;`)
  - Три отделни `www.* → apex` 301 redirects
  - HTTP→HTTPS redirect на трите едновременно
  - Origin Cert трябва да е multi-SAN или 3 отделни конкатенирани
- `env-templates/backend.env.example`: `ALLOWED_ORIGINS` и `CORS_ORIGINS` обхващат всички 6 origins (apex + www × 3 TLD)
- `env-templates/frontend.env.production.example`: добавени `REACT_APP_DOMAIN_BG/RO/EN`
- `group_vars/all.yml`: `domains` list разширен до 6

**Документация:**
- `INITIAL_DEPLOY.md` — пълен step-by-step (Phases 0–9): pre-flight, env fill, inventory, bootstrap, Postgres password setup, full site.yml, Cloudflare DNS+TLS (per zone), smoke tests, Stripe webhook config, lock-down, troubleshooting table.
- README обновено с трите домейна в архитектурната диаграма + ясно правило „кой домейн → кой език"

**nginx синтаксис проверен** ✅ (`nginx -t` минава с stub upstream)


- ab-front1 → public 178.105.37.1, private 10.0.0.2
- ab-back1 / ab-db1 → private 10.0.0.3 (no public IP)
- /etc/hosts на двете машини: ab-front1 10.0.0.2, ab-back1 10.0.0.3, ab-db1 10.0.0.3, ab-deploy 10.0.0.2 — кодът ползва имена, не IP.
- UFW: front1 публично 22/80/443; back1 само от 10.0.0.0/16 за 22/8001/27017/5432.



---

## Verified: Preauth Notification Bell + Bid Constraint Check (1 May 2026)

**Preauth Notification UI** (последна задача от предишната сесия) — ✅ VERIFIED.
- `GET /api/me/preauths` връща правилния shape: `[{auction_id, auction_title, max_amount_eur, used_eur, available_eur, auction_status}]`.
- `NotificationBell.jsx` рендерира секция `data-testid="preauth-section"` най-горе в dropdown-а с:
  - Заглавие: "ACTIVE PRE-AUTHORIZATIONS" (i18n key `inbox.preauth_title`)
  - `available_eur / max_amount_eur` форматирани като EUR
  - Прогрес бар (зелен) + процент налично
- Тествано чрез синтетичен preauth + login на `sectest_user@test.bg` → screenshot потвърждава визуализацията.
- Cleanup: synthetic preauth изтрит след теста.

**`triggered_extension` NOT NULL constraint** — ✅ NOT A REAL APP BUG.
- Schema: `bids.triggered_extension` е `BOOLEAN NOT NULL` без `server_default`.
- Application path (`services/bidding.place_bid()`) винаги задава `triggered_extension=triggered_extension` при ORM INSERT — потвърдено с реален end-to-end тест (bid placed OK, `triggered_extension=False`).
- Грешката от предишната сесия е причинена от ръчен raw SQL `INSERT` в bash, който е пропуснал колоната — не е production регресия.



---

## Hetzner Production Deploy Hardening (1 May 2026)

Permanent integration of all manual fixes that were applied during the
first live deploy onto Hetzner. **Repo now produces a clean deploy on a
fresh Ubuntu 24.04 box** without any manual touch-ups.

### Backend code
- `backend/translate.py` migrated from Emergent Universal Key →
  direct **Google Gemini SDK** (`google-generativeai==0.8.6`, already in
  requirements). Uses `GEMINI_API_KEY` env var. Free tier:
  https://aistudio.google.com/apikey. Falls back to `None` when key is
  missing (caller keeps original Bulgarian text).
- `emergentintegrations==0.1.0` removed from `requirements.txt`.
- `seed_admin()` now sets `email_verified=true` + `verification_required=false`
  on first install AND auto-heals existing admins on every boot — admins
  can never be locked out of `/admin` by a stale verification flag.
- `require_verified_email` early-returns for `role in ('admin','moderator')`.
- `apiClient.js` falls back to relative `/api/*` when `REACT_APP_BACKEND_URL`
  is empty → fixes cross-origin cookie loss when user navigates between
  `.com` / `.bg` / `.ro` (was THE root cause of admin "Не сте автентикирани"
  in production).

### Ansible
- `roles/common/tasks/main.yml`: SSH hardening reordered — deploy
  `authorized_keys` is installed FIRST, with an `assert` that fails the
  play when no key is configured. No more KVM-console rescue trips.
- `roles/backend/tasks/main.yml`:
  - Removed deadsnakes PPA (system `python3` works on Noble 24.04).
  - MongoDB 7.0 apt repo pinned to `jammy` (no `noble` channel yet).
  - venv created with `python3 -m venv` (was `python3.11`).
  - Pre-creates `{{ app_dir }}/scripts` before writing rollback.sh.
  - `backend.env` copy is **idempotent** — `force: no` + `stat` pre-check.
- `roles/frontend/tasks/main.yml`:
  - `yarn build` runs with `CI=false` (CRA lint warnings non-fatal).
  - `.env.production` copy is **idempotent** — `force: no` + `stat` pre-check.
- `group_vars/all.yml :: python_version` updated to `"3.12"` (informational).

### Systemd
- `autobids-backend.service`: uvicorn binds `0.0.0.0:8001` (was 127.0.0.1).
  Required because nginx on ab-front1 reaches the backend over private
  LAN (`ab-back1:8001` → 10.0.0.3:8001). UFW keeps 8001 closed to the
  public internet — only `10.0.0.0/16` allowed.

### Env templates
- `backend.env.example`: `POSTGRES_URL=postgresql+asyncpg://...` (driver
  prefix is mandatory for the async SQLAlchemy engine).
- `frontend.env.production.example`: `REACT_APP_BACKEND_URL=` empty by
  default with a long comment explaining why.

### Documentation
- `INITIAL_DEPLOY.md`: new "Production Quirks & Permanent Fixes" section
  documenting every quirk that was hit + how the repo handles it now.
- `README.md`: top-level changelog of post-deploy permanent fixes.

### Verified
- Backend healthy after restart (`curl /api/auctions/featured` → 200).
- Admin login (`admin@autoandbid.com` / `Nero08787`) → token + role=admin
  + email_verified=true → `/admin` panel renders without "Не сте
  автентикирани" (screenshot taken).
- `translate_text` import works without `emergentintegrations`; gracefully
  returns `None` when `GEMINI_API_KEY` is missing.

### Pending (next session — needs user input)
- Set `GEMINI_API_KEY` on production for translations to actually run.
- Set real `STRIPE_API_KEY` (`sk_live_...`) on production.
- Generate VAPID keypair on production: `npx web-push generate-vapid-keys`.
- Verify Resend SPF/DKIM for each TLD zone in Cloudflare DNS.


---

## Admin Tab Counters + Pre-launch Deindex Mode (1 May 2026)

### Admin tab badges
- New endpoint `GET /api/admin/counters` — single aggregate request returns
  counts for every admin tab (parallel `asyncio.gather` → ~1 DB round trip).
- `AdminPage.jsx` renders a green pill badge next to each tab label.
  Zero counts are hidden. 999+ truncation for very large numbers.
- Covers: **pending**, **all**, **users**, **requests**, **sold**, **unsold**,
  **archive**, **notifications**, **chat**.
- Verified with admin login: `All 3`, `Users 14`, `Archive 2`,
  `Notifications 29` render as badges. `data-testid="tab-<k>-count"` on each.

### Deindex mode (pre-launch SEO gate)
New admin setting **`deindex_mode`** (default: `false`). When toggled ON
from `/admin` → Settings → Deindex section, the site disappears from
every search engine without breaking login/API/admin/testing.

Four enforcement layers:
1. **robots.txt** — `/api/robots.txt` returns
   `User-agent: * / Disallow: /`. Nginx proxies `/robots.txt` →
   `/api/robots.txt` so the root URL crawlers hit is always live.
2. **HTTP headers** — `deindex_headers_middleware` in `server.py` stamps
   `X-Robots-Tag: noindex, nofollow, noarchive, nosnippet` on every API
   response.
3. **Meta tag** — `settings.js::applyVerificationTags` injects
   `<meta id="deindex-robots" name="robots" content="noindex,nofollow,noarchive,nosnippet">`
   into `<head>`. `seo.js::setPageMeta` detects the `data-global="1"`
   attribute and will NOT overwrite it during client-side navigation.
4. **Sitemaps** — `/api/sitemap.xml` and `/api/sitemap-images.xml` return
   404 so stale crawler-cached URLs stop reappearing.

### Explicitly NOT blocked
- Logins, authenticated API calls, admin panel — all work identically.
- Manual tester traffic (real users, internal QA) — unchanged UX.
- WebSocket live-bidding, push notifications, Stripe — all untouched.

### Cleanup
- Removed static `/app/frontend/public/robots.txt` (was
  `Allow: /` baked into the bundle — would conflict with dynamic one).
- Added nginx proxy rules for `/robots.txt`, `/sitemap.xml`,
  `/sitemap-images.xml` → backend.

### Verified
- `deindex_mode=true` → `/api/robots.txt` shows `Disallow: /` ✅
- `deindex_mode=true` → `/api/sitemap.xml` returns HTTP 404 ✅
- `deindex_mode=true` → `X-Robots-Tag` header on `/api/settings`,
  `/api/auctions/featured` ✅
- Browser DOM: `#deindex-robots` meta element present + survives
  SPA navigation ✅
- `deindex_mode=false` → everything reverts to normal (robots allows
  crawlers, sitemap 200, no X-Robots-Tag, meta removed) ✅

### Next Action Items (from previous sessions, still pending)
- 🔑 `GEMINI_API_KEY` on production (translations currently fallback to
  Emergent preview only)
- 🔑 `STRIPE_API_KEY=sk_live_...` + `STRIPE_WEBHOOK_SECRET=whsec_...`
- 📧 Verify Resend SPF/DKIM in Cloudflare DNS for `.bg` and `.ro` zones

### Future / Backlog
- P3: Cloudflare Turnstile CAPTCHA on registration
- P4: WebAuthn / Passkeys
- Refactor: split `server.py` (~4 300 LOC) into `routers/`

### Future / Backlog
- P3: Cloudflare Turnstile CAPTCHA на регистрация.
- P4: WebAuthn / Passkeys.
- Refactor: split `server.py` (4 200+ LOC) into `routers/`.

---

## 2026-05-02 — API payload optimization (view=list)

### Goal
Shrink the JSON payload of the three public list endpoints so homepage +
/auctions + /sales load dramatically faster. Typical auction document
carried ~19 KB each (full descriptions, 4 image arrays, specs, seller
info, contact fields). List cards only need ~30 fields + cover image.

### What changed

**Backend — `/app/backend/server.py`**
- Added `_LIST_KEEP` whitelist (30 fields) + `_list_shape()` helper that
  projects a public auction dict down to the minimum needed by
  `AuctionCard.jsx`. Images + thumbnails are sliced to the cover only.
- `GET /api/auctions?view=list` — returns trimmed items (both array and
  paginated shapes).
- `GET /api/auctions/featured?view=list` — returns trimmed array.
  Cache-Control: `public, max-age=30, s-maxage=60, stale-while-revalidate=120`
- `GET /api/auctions/sold?view=list` — returns trimmed array (or
  `{items,total,...}` when paginated). Cache-Control:
  `public, max-age=60, s-maxage=300, stale-while-revalidate=600`.
- `_LIST_KEEP` contains the **actual** field names emitted by
  `_public_auction()`: `featured` (not `is_featured`),
  `seller_is_verified_dealer` (not `seller_is_dealer`), `has_reserve`,
  `country`, `no_reserve`.

**Frontend — callers pass `view=list`**
- `lib/landingCache.js` — three homepage fetches.
- `pages/AuctionsPage.jsx` — main listing (paginated).
- `pages/SalesPage.jsx` — sold listing.
- `components/LiveTicker.jsx` — featured ticker.

### Verified
- Backend tests: `/app/backend/tests/test_payload_optimization.py` — 14/14
  green (trimmed / excluded fields, pagination, Cache-Control headers on
  localhost:8001).
- Payload reduction: **~93%** (37 KB → 2.5 KB for 5 auctions).
- Frontend: homepage (6 cards + LiveTicker + featured + sold), /auctions
  and /sales all render correctly with the trimmed payload (cards,
  titles, prices with VAT, no-reserve/featured/verified-dealer badges).
- Backwards-compat: legacy callers without `view=list` still get the full
  payload — zero breaking changes to `AuctionDetailPage`, admin rails,
  etc.
- Cloudflare preview edge rewrites Cache-Control to `no-store` — expected;
  production Nginx on Hetzner passes our headers intact.


---

## 2026-05-02 (later) — /auctions page speed push

### Goal
User: *"make the /auctions page lightning fast"*. Previous iteration shrank
payload ~93%. This one shaves server-side Mongo CPU + transfer and adds
an edge + client cache layer.

### What changed

**Backend — `/app/backend/server.py`**
- New `_LIST_MONGO_PROJECTION`: MongoDB exclusion projection that drops
  heavy fields (description, 4× image buckets, specs, documents, VIN,
  contacts, translations, service_history, rejection_reason, etc.)
  *before* they leave the DB driver. Wired into `GET /auctions`,
  `/auctions/featured`, `/auctions/sold` whenever `view=list` is set.
- `GET /auctions` skips `_has_high_value_preauth(viewer)` when
  `view=list` — saves one Mongo round-trip for every authenticated
  user (VIN is stripped anyway).
- `GET /auctions` anonymous responses now emit
  `Cache-Control: public, max-age=15, s-maxage=30, stale-while-revalidate=60`
  + `Vary: Cookie, Accept-Language`. Authenticated users still get
  dynamic responses. Production Nginx / Cloudflare will cache the hot
  default view and absorb the vast majority of /auctions traffic before
  it hits uvicorn.

**Frontend — `/app/frontend/src/pages/AuctionsPage.jsx`**
- SessionStorage cache (`autobid:auctions_default_v1`, 60 s TTL) for the
  *default* query only (page 1, `status=live`, `sort=ending_soon`, no
  filters, no search). On revisit the page paints instantly with cached
  cards while refetching in background — no loading spinner, no "No
  results" flash. Any filter / sort / search change bypasses the cache.

### Verified (`/app/test_reports/iteration_11.json`)
- Backend: 14/14 pytest green
- Frontend: homepage, /auctions, /sales all render correctly
- Cache-Control present for anonymous, absent for authenticated
- No regression in status/reserve computation
- Payload still ~93% smaller with `view=list`

### Result
Anonymous visitors on the default /auctions view now get:
1. First hit: 1.5 KB/card (vs 19 KB) + lean Mongo query with projection
2. Second hit within 30 s: served from Cloudflare edge (no backend hit)
3. Second client-side visit within 60 s: served from sessionStorage
   (no network hit at all, paints in <16 ms)


---

## 2026-05-02 (iter 12) — Auction detail page image load budget

### Goal
User: optimize image loading on /auctions/{id}. Hero = 400 px, side
thumbs = 400 px (browser shows ~100 px), hidden thumbs lazy, inline
interior shots = 400 px, lightbox = full-res loaded on demand only.

### What changed (frontend only — no backend)

**`/app/frontend/src/pages/AuctionDetailPage.jsx`**
- **Hero gallery `<img>`**: `a.thumbnails[photoIdx] || a.images[photoIdx]`
  (400 px instead of 1920 px). Added `decoding="async"` +
  `fetchpriority="high"`. Click still opens lightbox at
  full-resolution.
- **Side thumbs (5 visible)**: `a.thumbnails[i] || img` (400 px,
  displayed at ~100 px). `loading="lazy"` + `decoding="async"`
  preserved. Explicit `width=120 height=90` prevents layout shift.
- **Interior shots between description text**: now wrapped in a button
  (`data-testid=interior-shot-btn-{i}`) that calls
  `onOpenLightbox(interiorStartIdx + i)` — opens the lightbox at the
  correct global index so the user sees the *full-res* version on
  click. Image `src` uses the `thumbnails` slice for the interior
  bucket (since merged ordering is exterior + bumper + wheels +
  interior, we can cheaply derive the 400 px tier for interior from
  `a.thumbnails.slice(exteriorLen + bumperLen + wheelsLen)`).

**`/app/frontend/src/components/Lightbox.jsx`**
- New optional `thumbnails` prop. The thumbnail strip at the bottom now
  prefers `thumbnails[i]` over `images[i]` — strip used to load ALL
  1920 px originals.
- Lightbox main image: added `fetchpriority="high"` +
  `decoding="async"`.

### Result
For a fresh, categorized 24-photo auction with 400 px thumbs:
- **Cold load**: ~400 KB of images (1 hero × 400 px ≈ 25 KB + 5 side
  thumbs × ~8 KB + 3 interior × ~20 KB + strip thumbs in lightbox are
  deferred until lightbox opens). Previously was ~7-8 MB
  (24 × 300 KB full-res).
- Hidden thumbs beyond position 5 stay lazy — only load if the user
  ever scrolls the strip.
- Lightbox main image (1920 px, ~300 KB) loads *only* when the user
  explicitly opens it — and only the one they're viewing (each index
  change triggers one fetch).
- Click interior shot → lightbox opens at that exact photo in
  full-res.

### Verified (iteration_12.json)
- Frontend: 100% — hero/thumbs/interior/lightbox all use correct tier
- Backwards-compat with legacy auctions (external URLs,
  thumbnails == images) — confirmed renders without errors
- Zero regressions on homepage, /auctions, /sales
- Lightbox opens from hero, side thumb, "+N" overlay, and interior shot


---

## 2026-05-02 (iter 13) — Copy polish + i18n city import

### Copy changes (BG landing benefits block — `landing.steps.*`)
- `s1_desc`: "Преди първата наддавка" → **"Преди първото наддаване"**
- `s2_desc`: премахнат "и независим технически доклад" → **"Пълен фото
  отчет, сервизна история и VIN проверка."**
- `s3_desc`: "последните 2 минути удължават търга" → **"наддаване в
  последните 2 минути удължава търга"**
- `s4_desc`: "регистрация и финализиране" → **"прехвърляне и
  регистрация"**

### City import — Cyrillic support
- `backend/translate.py`:
  - New `transliterate_city_to_latin(name)` — accepts Cyrillic, returns
    Latin. Path: curated `_CITY_OVERRIDES` fast-dict (≈40 big BG cities,
    no LLM call) → Gemini (if `GEMINI_API_KEY`) → Emergent universal key
    → ISO-9 deterministic char-map fallback.
  - New `country_from_host(host)` — `.bg` → Bulgaria, `.ro` → Romania,
    `.com` → Bulgaria (default). Used so mobile.bg imports pre-fill the
    country based on which tenant the user is on.
- `backend/server.py` — `/auctions/import-mobile-bg` now:
  - Transliterates the Cyrillic city before returning it.
  - Adds a `country` field to the response based on request Host.
- `frontend/src/pages/SellPage.jsx`:
  - Dropped the client-side Latin-only regex + HTML `pattern` attr.
  - New placeholder: `"Sofia, София, Bucharest, Plovdiv…"`.
  - Import flow now consumes `data.country` and pre-fills the form.
- `i18n/locales/{bg,en,ro}.json`: `sell.form.city_hint` updated to
  "Приемаме и кирилица, и латиница." / "We accept both Latin and
  Cyrillic script." / "Acceptăm atât alfabetul latin, cât și chirilic."

### Mobile.bg image dedup fix
Problem: mobile.bg galleries embed each photo twice (thumbnail + big).
Old import accepted 7+ low-res dupes alongside the real high-res files.
Fix in `/auctions/import-mobile-bg`:
- `_canon(url)`: strip size folders (`/big/`, `/small/`, `/thumb/`, …),
  strip size suffixes (`_big.jpg`, `_t.jpg`, …), strip numeric size
  prefixes (`/8-name.jpg`), strip querystring → canonical photo key.
- `_score(url)`: resolution score — `/big/` > standard > `/small/` /
  `/thumb/`.
- Keep the highest-scoring URL per canonical key, preserve first-seen
  ordering.
- Result: 9 URLs → 5 best-resolution URLs, no low-res leftovers.

### Verified (iteration_13.json)
- Backend: 44/44 pytest green
- Frontend: 100%, BG locale shows the 4 updated phrases, EN/RO render
  cleanly, SellPage no longer has `pattern` or regex restriction.
- Unit: `transliterate_city_to_latin`, `country_from_host`, image dedup
  helpers all verified.


---

## 2026-05-02 (iter 14) — Mobile.bg import: real-world photo dedup

### Goal
User reported: a 17-photo mobile.bg listing was importing 24 photos —
the last 7 being low-res dupes of the first 7. Sample URL:
`https://www.mobile.bg/obiava-11772388504582211-bmw-m2-competition-swiss-hk-carplay`.

### Root cause (after scraping the actual page)
1. Mobile.bg gallery HTML contains **two** img sets with deterministic
   parallel filenames:
   - `.owl-carousel` items → `/big1/<id>_<code>.webp` (high-res, 17 items)
   - `.newAdImages .smallPicturesGallery` → `<id>_<code>.webp` without
     the `/big1/` segment (~120 px thumbs, 17 items)
   → 34 candidates total; iter-13 regex `/(big|small|…)/` didn't match
   `big1` so canonical keys diverged and both variants survived.
2. The scraper also picked up photos from the **"Още обяви в mobile.bg"**
   related-listings block at the bottom of the page — unrelated cars
   sneaking into our import.

### Fix (`/app/backend/server.py` `/auctions/import-mobile-bg`)
- Restrict image search to the main gallery scope
  (`#rezon-gallery` → `.owl-carousel` → `.newAdImages` → first
  `<section>` fallback). Related-listings thumbnails are now outside
  our scan.
- Added `focus.bg` to the allowed host list (mobile.bg serves photos
  from `mobistatic*.focus.bg` / `cdn*.focus.bg`).
- Added `data-src-gallery` as a fallback attribute when reading URLs.
- **Canonical dedup key = filename only** — mobile.bg assigns the same
  deterministic `<listingId>_<code>.webp` name to the big and small
  variants (only the directory differs). Filename-based keying is also
  robust to future CDN path renames.
- Updated `_canon` regex to strip `big\d*` (big1, big2…), and `_score`
  to match `/big\d*/` as highest-resolution marker.

### Result
- Real BMW M2 listing (17 photos): **17 returned, all `/big1/`**, in
  exact page gallery order, zero dupes, zero bleed-through from
  related listings.
- iteration_14.json: **16/16 backend tests pass, 0 issues**.


---

## 2026-05-02 (iter 15) — Landing hero dedup

User: the auction shown in the landing hero must NOT appear again
in the sections below.

### Fix — `/app/frontend/src/pages/LandingPage.jsx`
- Compute `hero = featured[0] || auctions[0]` as before.
- Derive two filtered lists once: `auctionsEx`, `featuredEx` — both
  exclude the `hero.id`.
- `Active auctions` grid now renders `auctionsEx.slice(0, 6)`.
- `Selected editorial` grid renders `featuredEx.slice(0, 6)`.
- The editorial section gate changed from `featured.length > 1` to
  `featuredEx.length > 0` (correct semantics: show the rail as long
  as there's at least one non-hero featured car).

### Verified
- Preview BG: hero = BMW M240i xdrive M-Performance; `Active auctions`
  below shows only BMW M2 Club sport + Mercedes-Benz C 43 AMG — no
  duplicate of the hero car.
- No backend changes.


---

## 2026-05-02 (iter 16) — Hero = full AuctionCard + mobile sticky header

### Task 1: Hero shows full AuctionCard
`LandingPage.jsx`: replaced the custom hero layout (image + inline title
+ current bid column) with a plain `<AuctionCard auction={hero} />`
wrapped in the same `data-testid="hero-featured-auction"`. Hero now
shows: time-remaining overlay, FEATURED badge, title, year, mileage,
fuel, location, current bid, bid count, and No-reserve / VAT badges —
identical to every other card on the site.

### Task 2: Mobile sticky header (BaT-style)
`AuctionDetailPage.jsx`:
- New `stickyVisible` state + `titleRef` on the `<h1>`.
- `IntersectionObserver` with `rootMargin: "-56px 0px 0px 0px"` (site
  header height) watches the `<h1>`. When the title scrolls out of view
  (`!entry.isIntersecting`), the sticky bar slides into view.
- Bar is `fixed top-[56px]` (right under the main header), `z-40`,
  `lg:hidden`, CSS transform `translate-y-0` ↔ `-translate-y-full` with
  `transition-transform duration-300 ease-out`. Gives the exact
  slide-down / slide-up behaviour the user requested.
- Content: title (truncate), time-remaining, current bid (gross when
  VAT-inclusive), comments count with icon, circular watchlist heart
  button, primary **Bid** button that smooth-scrolls to the bid input
  and auto-focuses it 400 ms later. Sold/Ended states swap the Bid
  button for a small "Продаден"/"Завършил" label.
- All elements have `data-testid=sticky-{title,time,bid,comments,watch-button,bid-button}`.

### Verified
- 390×844 viewport: sticky's bounding box `y=-3` before scroll (off
  screen) → `y=55.6` after scroll (pinned under header). Fields
  populated: "BMW M240i xdrive M-Performance", "5д 13ч", "5000 €", "1"
  comment, watch button present, "Наддавай" CTA.
- 1920 viewport: sticky correctly hidden via `lg:hidden`.
- Hero card at 1920 shows full AuctionCard with 5D 13H / FEATURED /
  2017 / 95 000 км / Petrol / Sofia, Bulgaria / 5000 € / 0 bids / No
  reserve.


---

## 2026-05-02 (iter 17) — Copy + bid steps + hero size + sticky polish

### 1. "Подай наддаване" → "Наддавай"
`i18n/locales/bg.json` → `auction.place_bid` updated.

### 2. Bid steps halved across ALL brackets
`backend/helpers.py` `bid_step()` + `frontend/pages/AuctionDetailPage.jsx`
`bidStepFor()`:
| current bid | old step | new step |
|---|---|---|
| €0-1k | €50 | **€25** |
| 1k-5k | 100 | **50** |
| 5k-10k | 250 | **125** |
| 10k-25k | 500 | **250** |
| 25k-50k | 750 | **400** |
| 50k-100k | 1000 | **500** |
| 100k-200k | 2000 | **1000** |
| 200k-500k | 5000 | **2500** |
| 500k-1M | 10000 | **5000** |
| 1M+ | 25000 | **10000** |

Verified backend: `bid_step(500)=25, bid_step(2000)=50, bid_step(7000)=125, …`
Verified frontend: bid input `min=5125, step=125` for 5000€ auction.

### 3. Desktop hero shrunk
`LandingPage.jsx`: `lg:col-span-6/6` → `lg:col-span-7` (copy) + `lg:col-span-5`
(hero) with `lg:justify-self-end lg:max-w-[420px]`. Result at 1440: hero card
= 420×577 (was ≈720 wide). Standard auction-card footprint on desktop.

### 4. Mobile sticky header redesigned
`AuctionDetailPage.jsx` sticky block:
- Font sizes bumped: title `15px → 17px`, meta row `11px → 13px`, bid `→15px`.
- **Current bid bolded and moved to leftmost slot** of the meta row
  (`font-mono font-bold tabular-nums text-[15px] text-ink`).
- Comments counter removed; replaced with **bid counter** `<Gavel /> {bid_count}`
  (`data-testid="sticky-bid-count"`).
- Watch button upgraded to 40×40 (was 36×36), CTA button padding ++, icons ++.
- All `data-testid`s preserved (`sticky-title`, `sticky-bid`, `sticky-time`,
  `sticky-bid-count`, `sticky-watch-button`, `sticky-bid-button`).

### Verified
- Desktop hero 420×577 at 1440 viewport.
- Mobile sticky fields populate correctly; comments element no longer exists
  in DOM (verified via `document.querySelector` returning null).
- Bid step `500€ → min €5,125, step €125` (0→1000 bracket is €25, 1k-5k €50,
  5k-10k €125 ✓).


---

## 2026-05-02 (iter 18) — Always-on mobile sticky + 2-hero + i18n time

### 1. Mobile sticky header: always visible, pt-15
`AuctionDetailPage.jsx`:
- Removed `stickyVisible` state + IntersectionObserver. Bar is now
  unconditionally pinned at `top-[56px]` — no slide-in/slide-out, no
  disappearing during scroll.
- Internal padding: `pt-[15px]` (was `py-2.5`) for the 15 px top margin.
- `<main>` gets `pt-[76px] lg:pt-0` so the fixed sticky never covers
  page content.
- The desktop `<h1>` gets `hidden lg:block` — on mobile, only the
  sticky's `sticky-title` is rendered, eliminating the duplicate title
  the user complained about.

### 2. Time-remaining labels translated
Replaced the hardcoded `{tl.label}` (Bulgarian-only `д / ч / м / с`) in
the sticky with `formatTimeLeft(tl, t)`, which looks up the i18n keys
`time.days_hours`, `time.hours_minutes`, `time.minutes_seconds`,
`time.ended` — already defined in `bg.json / en.json / ro.json`.
Verified live: BG `5д 12ч`, EN `5d 12h`, RO `5z 12h`.

### 3. Two hero picks with smart auto-selection + 30 min stickiness
New backend endpoint `GET /api/auctions/hero`:
- Pulls every live, non-archived auction.
- Scores each: `score = (featured_flag × 1000) + (bid_count × 10) + comments_count`.
  Featured flag dominates; bids + comments break ties.
- Returns the top 2 picks in list-shape, plus
  `Cache-Control: public, s-maxage=300, stale-while-revalidate=600`.
- **Stickiness**: picks are cached in module memory (`hero_picks._cache`)
  for 30 min. On subsequent calls, the two cached ids are re-validated
  (still live, not archived, `ends_at` still in the future); if valid,
  the same pair is returned. If either pick has ended/been pulled, a
  fresh top-2 is chosen immediately.

`landingCache.js` now fetches `/auctions/hero` in parallel and
persists the result. `LandingPage.jsx`:
- `heroes = heroPicks.slice(0, 2)` with fallback to featured/auctions.
- Heroes render in a **responsive 2-col grid** on md+ (stacked on
  mobile) inside the existing `hero-featured-auction` container.
- `heroIds` set filters both `featuredEx` and `auctionsEx` so neither
  hero car appears twice on the page.

### Verified
- `curl /api/auctions/hero` → 2 picks (featured BMW M240i first, then
  BMW M2). Second call → identical ids (cache hit).
- Mobile: sticky pinned at `y=56px` with `pt-[15px]`, H1 hidden, all
  three locales render time correctly.
- Desktop: both heroes render side-by-side in the hero section, no
  duplicates further down the page.

