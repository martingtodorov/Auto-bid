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

## Still MOCKED
- **Stripe Pre-authorization is MOCK** — no real PaymentIntent is created. Card data is not sent anywhere. When a real Stripe key is added, swap `mock_pm_...` flow in `place_bid` for `stripe.PaymentIntent.create(capture_method="manual")` and confirm/cancel on outbid/finalize.

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
