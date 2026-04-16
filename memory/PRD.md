# AutoBid.bg — PRD

## Original Problem Statement
> "create me a landing page for a car auction website similar to cars and bids and bring a trailer, but in Bulgarian"

User choices (from ask_human):
- Brand: **AutoBid.bg**
- Style: Modern (upgraded from initial "classic editorial") — Manrope geometric sans, rounded cards, pill buttons, green gradient accent, live ticker
- Sections: Landing + full browseable dashboard with filters and bidding
- Full functional application (auth, bidding, comments, sell flow)
- Sample listings from mobile.bg

## Architecture
- **Backend**: FastAPI + motor (Async MongoDB) + bcrypt + PyJWT. All routes under `/api`. Collections: `users`, `auctions`, `bids`, `comments`, `watches`, `login_attempts`.
- **Frontend**: React 19 + React Router 7 + Tailwind + lucide-react icons, Manrope / IBM Plex Mono fonts.
- **Auth**: JWT (HS256) with Bearer token in `Authorization` header, stored in `localStorage`.

## User Personas
1. **Купувач / Bidder** — brows auctions, places bids, leaves comments, watches auctions.
2. **Продавач / Seller** — submits a car via `/sell`, awaits editorial approval.
3. **Администратор** — seeded admin (`admin@autobid.bg`) for moderation.

## Implemented (2026-04-16)
- JWT auth: register, login, /auth/me; bcrypt hashing; admin seeded on startup.
- Auctions CRUD: list with filters, facets, featured, sold archive, detail view.
- Bidding: min increment +€100, anti-sniping (extend 2 min), block seller self-bidding.
- Comments per auction. Watchlist toggle. "Sell your car" submission creating pending auctions.
- Seed: 12 live + 4 sold auctions from mobile.bg listings.
- Landing page, Browse, Auction detail, Sales, How it works, Sell, Dashboard, Login, Register.
- **Live ticker** marquee at top with pulsing LIVE indicator.
- Modern Manrope UI: pill buttons, rounded cards, ambient gradient hero, glass navigation.

## Iteration 2 (2026-04-16)
- **Real-time WebSocket** `/api/ws/auctions/{id}` — broadcasts bids + comments to all viewers; frontend subscribes in AuctionDetailPage with status indicator, 25s keepalive.
- **5% pre-authorization flow (MOCK Stripe)**: Each bid requires `payment_method_id`. Backend stores `preauth_id`, `preauth_status` (`authorized|released`), `preauth_amount_eur` per bid. On outbid: previous user's preauth auto-released + email. On auction finalize (admin): winner's preauth released. Full PreauthModal UI with card form (mock tokenization).
- **Resend emails** (`/app/backend/emails.py`): outbid, auction won, seller approved, seller rejected. Bulgarian HTML templates. Gracefully logs to console when `RESEND_API_KEY` not set.
- **Admin panel** `/admin` (role=admin only): list pending submissions, approve (→ live auction), reject with reason (→ email seller), finalize live auctions (→ releases preauths, marks sold, emails winner).
- **Image uploader** on `/sell`: drag-free file input, auto-compression to 1600px JPEG (quality 82) → base64, stored in MongoDB, up to 8 photos. First photo is cover.
- Card detail on bids list shows "preauth активен" indicator.

## Iteration 5 (2026-04-16)
- **Reserve-not-met post-auction flow**: ended auctions with unmet reserve auto-transition to `reserve_not_met` status. Seller gets actions: `POST /auctions/{id}/accept-high-bid` (→ sold at current) or `POST /auctions/{id}/counter-offer` with price. High bidder sees counter-offer banner on detail page and responds via `POST /auctions/{id}/counter-offer/respond` (accept → sold at counter price; decline → ended).
- **Seller edit/withdraw**: `PATCH /auctions/{id}` (title/description/starting/reserve/images) restricted to owner+admin; allowed while pending, rejected, or live with 0 bids. `DELETE /auctions/{id}` marks as `withdrawn`, releases any preauths.
- **Public user profile** at `/profile/:userId`: new endpoint `GET /users/{user_id}/profile` returns user meta + stats + listings_sold + purchases + active_listings. Excludes email/password. Profile page shows avatar initial, member year, sales/purchases/active/rating stat cards, and tabs for each.
- Auction detail links `seller_name` → `/profile/:sellerId` and each bid's/comment's `user_name` → `/profile/:userId`.
- MyListings page gets inline edit form, Withdraw button, and reserve-not-met action card (Accept highest / Counter-offer with price input).
- Auction detail shows counter-offer banner with Accept/Decline buttons when `counter_status=pending && counter_offer_to == current user`.
- Backend verified: PATCH pending, DELETE→withdrawn, counter-offer flow end-to-end (€2500 sale after accepted counter on Fiat Panda reserve €50k).
- **Reserve price logic**: AuctionCreate already had `reserve_eur`. Now:
  - `_public_auction()` helper injects `has_reserve: bool`, `reserve_met: bool|null` on every auction response.
  - `reserve_eur` is **hidden** from bidders — only seller (owner) and admin see the exact number.
  - 3 seed cars now carry reserves (BMW X5, BMW M3, Porsche 911) to showcase mixed states.
- **"Резервът е достигнат" indicator** on cards (green live pill) and on detail bid box. Non-met state shows grey dot. "Без резерв" pill shown for no-reserve auctions.
- **Seller dashboard `/my-listings`**: `GET /me/listings` returns seller's own auctions with full detail including hidden reserve. Page shows status pills (pending/live/sold/rejected/ended), current bid/countdown, rejection reason display, CTA to view or create new. Linked in Nav as "Мои обяви".
- **Pre-authorization reduced to 3%** (from 5%) — matches buyer's premium.
- **3% buyer's premium commission** captured from winner's preauth on `POST /admin/auctions/{id}/capture-premium` (new endpoint). Bid `preauth_status` transitions: `authorized → captured`. Losing bidders' preauths released in same operation. Auction marked `sold` with `premium_captured=True`, `premium_amount_eur` stored.
- Kept `POST /admin/auctions/{id}/finalize` which releases ALL preauths (no commission captured).
- **New `GET /admin/sold`** endpoint: returns sold auctions with winner info, commission owed, preauth capture state.
- **Admin panel** gets Tabs (Pending | Sold). Sold tab shows table with Capture 3% / Release actions per auction and "Преведено" badge once captured.
- **`GET /auctions/{id}/watch-status`** endpoint added. Watch button on auction detail page now reflects state + toggles.
- **User-facing `/watchlist` page** lists followed auctions (uses existing `/me/watchlist`).
- Nav adds "Следени" link for authenticated users.
- How-it-works page updated to 3% buyer's premium copy.

## P1 Next
- Replace MOCK Stripe with real Stripe PaymentIntents once keys are obtained.
- Provide Resend API key to activate real emails (set `RESEND_API_KEY` in `/app/backend/.env`).
- User-facing watchlist page + wire Watch button on detail page.
- Admin view of sold/finalized auctions with capture actions.

## P2
- Reserve / no reserve logic fully surfaced in UI.
- Advanced search (text query).
- Seller profile pages, ratings.
- Vehicle history reports integration.

## Test Credentials
See `/app/memory/test_credentials.md` — admin@autobid.bg / admin123.

## Next Action Items
- Connect real-time bid updates (WebSocket) once traffic > baseline.
- Add Stripe buyer-fee collection at auction close.
- Wire watch button on detail page to existing `/me/watchlist` endpoints.
