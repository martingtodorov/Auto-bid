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
