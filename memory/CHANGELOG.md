# Changelog

## 2026-05-04 — Iteration 15: Refactor + Bid Confirmation UX

### Backend refactor (server.py → routers/)
- Изнесена Leaderboard логика в `/app/backend/routers/leaderboard.py`
  (60s in-memory cache, supports types: sellers / commenters / bidders / reputation, periods: all / month).
- Изнесени Watchlist endpoints в `/app/backend/routers/watchlist.py`:
  `/auctions/{id}/watch-status`, `/auctions/{id}/watch`, `/me/watchlist`,
  `/me/listings`, `/me/bids`.
- Поправен blocker `IndentationError` в `server.py` (дублиран `request_vin` блок след refactor).
- 29/29 backend integration tests pass (`/app/backend/tests/test_iteration15_refactor_validation.py`).

### Bid Confirmation Modal (frontend)
- Нов компонент `/app/frontend/src/components/BidConfirmModal.jsx`.
- При натискане на "Наддай" в `AuctionDetailPage`:
  - Ако `bidding_credit.max_amount_eur >= bid_amount_net` → показва се
    `BidConfirmModal` overlay с:
      - текущото наддаване (gross + net + ДДС breakdown),
      - оставащ кредит след наддаването,
      - бутон "Зареди още" (отваря `BiddingCreditModal` за top-up),
      - primary CTA "Наддай {amount}" (директен POST към `/auctions/{id}/bids` без Stripe).
  - Ако кредитът не покрива → продължава да отваря `BiddingCreditModal`
    (Stripe Checkout flow за нова авторизация).
- Manual release на authorization в `/my-bids` страницата вече работи
  чрез `POST /api/stripe/authorizations/{auth_id}/release` с server-side
  guard (409 ако user е leading bidder на live търг).
- Nav credit counter и mobile menu вече линкват към `/my-bids`.

### Files touched
- `/app/backend/server.py` (-7 lines, syntax fix)
- `/app/frontend/src/pages/AuctionDetailPage.jsx` (+ BidConfirmModal wiring)
- `/app/frontend/src/components/BidConfirmModal.jsx` (NEW, 159 lines)

### Tested
- Backend: testing_agent_v3_fork, 29/29 PASS, success_rate: 100%
- Frontend smoke: homepage loads cleanly with featured listings, no console errors.

## 2026-05-05 — Iteration 16: Active Bids (leading + outbid) + Mobile Credits + Leaderboard i18n

### Backend
- `GET /api/me/preauths` rewritten — пуска заявка към PG за всички бидове
  на потребителя, дедупира по auction_id, обогатява от Mongo и връща
  всеки live търг с `is_leading: bool`, `user_max_bid_eur`,
  `current_bid_eur`. Връща и leading и outbid аукционите. Запазени са
  backwards-compat полетата `max_amount_eur`, `available_eur`, `used_eur`.
- `GET /api/stripe/authorizations/my-credits` — добавено ново поле
  `outbid_bids[]` (auctions where user has bid but is currently outbid).
  Кредитът остава непокътнат — потребителят може да наддава отново
  без нов Stripe charge.

### Frontend
- `NotificationBell.jsx` пълно пренаписан (counter-fixed broken JSX от
  предишната сесия). Section data-testid="active-bids-section" показва
  и leading (зелен badge "Водите/Leading/În frunte"), и outbid (амбър
  badge "Надминати/Outbid/Depășit") с visual delineation чрез
  border-l-2.
- `MyBidsPage.jsx` — нова section data-testid="my-bids-outbid" показва
  outbid аукциони с amber styling, Текущ/Ваш bid pricing.
- `CreditsOverlay.jsx` — вече използва `createPortal(document.body)`
  с `fixed inset-0 z-[60]` → центрира коректно както на десктоп, така
  и на мобилно (verified в test_report).

### i18n (BG/RO/EN)
- `inbox.active_bids_title`, `inbox.bid_leading`, `inbox.bid_outbid`,
  `inbox.your_bid`, `inbox.current_vs_yours` — нови ключове.
- `my_bids.outbid_title` — нов ключ.
- `leaderboard.*` — пълно намерение (subtitle, all_time, month,
  tab_reputation/sellers/commenters/bidders, metric_*, empty, meta_*).

### Tested
- testing_agent_v3_fork (iteration_16.json) — 18/18 backend PASS,
  11/11 frontend UI verified, 0 critical, 0 action items.


## 2026-05-05 — Iteration 17: Quick re-bid + WebSocket live updates + Stripe lifecycle

### Frontend (A + B)
- Нов helper `/app/frontend/src/lib/bidUtils.js` — `bidStepFor`, `minNextBid`. Shared между AuctionDetailPage и MyBidsPage.
- `MyBidsPage.jsx`:
  - Quick re-bid button под всяка карта (commitments + outbid_bids) `my-bids-quickbid-<auction_id>`. Click → `GET /auctions/{id}/next-bid` → `window.confirm` → `POST /auctions/{id}/bids`.
  - WebSocket multi-subscription: per auction_id отваря WS към `/api/ws/auctions/{id}`. На `bid` event → debounced reload (500ms). Замества polling.
- i18n `my_bids.quick_bid_cta`, `quick_bid_confirm`, `bid_placed` (BG/RO/EN).

### Backend (C + D)
- Нов модул `/app/backend/services/stripe_lifecycle.py`:
  - `_create_offsession_hold` — нов PI с `off_session=True, confirm=True, capture_method=manual` срещу запазена PM.
  - `extend_expiring_authorizations` — сканира active account-level holds expiring в следващите 24h, заключва чрез `extension_locked_until` (6h), reissue нов hold, освобождава стария.
  - `capture_and_reissue` — partial-capture на buyer fee → marks old captured → re-issues нов hold за непохарченото (универсалният credit pool остава funded). Stripe auto-releases при partial-capture.
  - `start_worker` / `stop_worker` — фонов цикъл (3600s, initial delay 60s).
- `_auction_finalizer_loop` sold branch → след per-auction capture loop сега ползва `capture_and_reissue` за account-level holds на winner-a (sorted oldest-first).
- Нов admin endpoint `POST /api/admin/stripe/lifecycle/scan` (admin-only).

### Tested
- testing_agent_v3_fork (iteration_17.json) — 19/19 backend + 13/13 frontend, 0 critical, 0 action items.
- Stripe TEST MODE: actual roundtrip blocked в dev; production има валидни keys в backend.env.



## 2026-05-05 — Iteration 18: Credit Expiring Banner + Push Notifications

### Backend
- Нов helper `_emit_expiring_alert` в `services/stripe_lifecycle.py`. Идемпотентен (collection `lifecycle_alerts_sent`), извиква `routers.inbox.notify_user(type='credit_expiring', link='/settings', push_template_id=…, push_kind=None)` за in-app notification + Web Push (bypass opt-out защото е operational alert).
- `extend_expiring_authorizations` emit-ва alert при `no_saved_pm` и `card_declined` пътищата.
- Push templates `credit_expiring_no_pm`, `credit_expiring_declined` (BG/EN/RO).
- Нов endpoint `GET /api/stripe/authorizations/expiring` → `{has_expiring, reason, expires_at, hold_id}`. Reason идва от най-скорошния `lifecycle_alerts_sent` row.

### Frontend
- Нов компонент `CreditExpiringBanner.jsx` (червена ивица под header). 3 copy варианта (no_saved_pm / card_declined / default). CTA → `/settings`. Dismiss → localStorage за 12h. Poll 10 мин.
- Wired в `App.js` между TwoFactorPromptBanner и LiveTicker.
- i18n `credit_expiring.*` (BG/EN/RO).

### Tested
- testing_agent_v3_fork (iteration_18.json) — 23/23 backend + UI verified, 0 critical, 0 action items.
