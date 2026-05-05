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

