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

