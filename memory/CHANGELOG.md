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

## 2026-05-05 — Iteration 19: Removed custom OG image template

### Backend
- `routers/seo.py /share/auction/{id}` — `og:image` и `twitter:image` сега сочат директно към headline image на търга (`headline_image_url(auction)`). Премахнати `og:image:width/height/type=image/png` meta tags (защото headline снимките могат да са JPG/WebP в различни размери).
- `routers/seo.py /og/auction/{id}.png` — превърнат от Pillow generator в 302 redirect към headline image (backwards-compat за crawler caches).
- `services/og_image.py build_and_persist` — опростен до `return headline_image_url(auction)`. Никакви Pillow композиции, файлове на диск, cache busters. Pillow-related helper-и (`build_or_cache`, `_compose_image`) остават в файла за бъдеща употреба, но никой не ги извиква.
- Fallback chain: headline → `og_image_url` (legacy) → `/og-default.jpg`.

### Защо
- Pillow-rendered PNG-ите се държаха непредсказуемо: Facebook кешираше остарели версии, WhatsApp обрязваше bid badge-а, Telegram re-encoded-ваше типографията. Реалната снимка на колата е най-надеждното social preview.

### Tested
- testing_agent_v3_fork (iteration_19.json) — 14/14 backend, 0 issues.
- Manual smoke: `og:image` вече сочи към `mobistatic4.focus.bg/.../11774653575320034_hr.webp` (реалния headline на live auction).


## 2026-05-12 — Iteration 20: Image CDN architecture + Mobile swipe + Pinch-zoom

### Backend
- Нов модул `services/image_variants.py` — генерира 12 варианти на снимка (AVIF q50 / WebP q75 / JPG q82) × 4 размера (200 thumb / 600 card / 1200 gallery / 1920 full). Content-addressed по sha256 → re-uploads безплатни. Disk layout: `<UPLOAD_DIR>/variants/<aa>/<bb>/<sha>/<size>.<ext>`.
- HEIC support added (pillow_heif 1.3.0) — iOS uploads работят native без user conversion.
- EXIF auto-rotate чрез `ImageOps.exif_transpose` — phone uploads излизат правилно ориентирани.
- `public_variant_url()` респектира `IMAGE_CDN_BASE` env var → когато е празно (dev), URLs са relative `/api/uploads/variants/...`; когато е set (production), стават absolute `https://img.autoandbid.com/variants/...`. Готов за CDN subdomain без code промени.
- `POST /api/auctions` + `POST /api/auctions/import-mobile-bg` сега генерират variants и записват `images_variants[]` на auction документа.
- `_list_shape` slice-ва `images_variants` до първите 4 (за mobile swipe deck).

### Frontend
- Нов компонент `Picture.jsx` — AVIF → WebP → JPG fallback chain с retina-aware srcSet (1x/2x density steps). Graceful fallback към plain `<img>` за legacy auctions.
- `AuctionCard.jsx` пренаписан с horizontal scroll-snap carousel (touch-action: pan-x → не блокира vertical scroll). 4 photo slides + 5th "View full auction" CTA slide (`auction-card-cta-slide`). Pagination dots, IntersectionObserver tracks active slide.
- `AuctionDetailPage.jsx` hero + thumbstrip ползват `<Picture>` с `priority` за LCP optimization.
- Premium UX: First image на mobile цена loaded eager + fetchpriority=high; lazy за останалите.

### UX fixes
- Premium pinch-zoom: премахнат `maximum-scale=1, user-scalable=no` от viewport meta + изтрит gesturestart blocker + double-tap watchdog от `index.js`. iOS Safari + Android Chrome вече позволяват zoom.
- Sell page image reorder scroll lock: `onDragStart` сетва `body.style.overflow = "hidden"` (HTML5 desktop drag), restored на `onDragEnd`. Mobile touch drag вече има scroll lock от преди.

### i18n (BG/EN/RO)
- `auction.view_full_auction`: "Виж пълния търг" / "View full auction" / "Vezi licitația completă".

### Tested
- testing_agent_v3_fork (iteration_20.json) — 27/27 backend, 100% frontend UI verified, 0 issues, 0 action items.
- Manual smoke: seeded test auction with variants → 4 `<picture>` elements + 1 CTA slide в card, 5 `<picture>` elements в detail. Pinch-zoom потвърден active.

