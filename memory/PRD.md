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
- Auctions CRUD: list with filters (make, fuel, transmission, region, body_type, price, year, status, sort), facets endpoint, featured, sold archive, detail view.
- Bidding: min increment +€100, anti-sniping (extend 2 min when bid within final 2 min), block seller self-bidding.
- Comments per auction. Watchlist toggle. "Sell your car" submission creating pending auctions.
- Seed: 12 live auctions + 4 sold archive, based on mobile.bg real-world listings (Audi A8, BMW X5/M3/M5, Porsche 911, Alfa Giulia/159/MiTo, VW Passat, Toyota RAV4, Mercedes E/G-Class, Audi RS6, Lexus LC500, Citroen C5X, Kia Niro).
- Landing page: Hero + ambient gradient, active auctions grid, "Как работи", featured editorial, last sales, CTA.
- Auctions browse page with left filter rail, mobile slide-over, sort.
- Auction detail: photo gallery with thumbnails, specs table, description, live bid box (sticky), bid history, comment section.
- Pages: Sales archive, How it works, Sell car, Dashboard (my bids), Login, Register.
- **Live ticker** at top of every page — marquee of live auctions with pulsing LIVE indicator.
- All copy in Bulgarian.
- Backend verified via 17 curl tests (auth, filters, bidding, comments, authz).

## P1 — Nice to have next
- Real-time updates via WebSocket for bids / comments (currently re-fetch).
- Email notifications (SendGrid / Resend) — outbid / auction won / reserve met.
- Stripe "Safe Purchase" escrow + buyer's premium payment.
- Auction approval admin panel (currently seller submissions go to `pending` but no UI).
- Watch button persistence on detail page (endpoint exists, UI not wired).
- Image uploader instead of URL paste on `/sell`.

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
