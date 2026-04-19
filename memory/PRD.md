# AutoBid.bg — PRD (Product Requirements Document)

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
- Admin seed account (admin@autobid.bg / admin123)
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
- **P1** Real Stripe API integration (сега MOCKED — preauth/capture са симулирани)
- **P2** "Buy Now" функционалност (фиксирана цена, подобно на BaT Rarities)
- **P2** Sold Price Tracker (публична статистика за приключили сделки)
- **P2** Рефакторинг на `server.py` (2500+ реда) → изнасяне на `admin` и `auctions` routes
- **P3** CAPTCHA при регистрация (hCaptcha/Cloudflare Turnstile)
- **P3** WAF layer (SQLi/XSS pattern matching)
- **P3** Email templates estetic upgrade

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

## 3rd-party integrations status
- Resend: Configured via env (RESEND_API_KEY), fallback console log
- Twilio: Configured via env (TWILIO_*), fallback console log
- Stripe: **MOCKED** (mock_pi_* tokens, 2% buyer premium simulation)

## Critical notes for future agents
- НЕ използвайте npm, само yarn
- Всички backend routes трябва да са с `/api` префикс
- `_auction_status()` е computed при четене — stored статуси: pending/rejected/withdrawn/removed/sold/reserve_not_met/ended/live
- При създаване на нови компоненти с форми: НИКОГА не дефинирайте sub-компоненти ВЪТРЕ в родителския компонент (причинява loss of focus bug)
