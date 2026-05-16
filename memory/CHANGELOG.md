# Changelog


## 2026-05-16 — Iteration 20: Submit + import performance optimization

### Bottleneck
`/auctions` POST and `/auctions/import-mobile-bg` were generating
AVIF/WebP/JPG × 4 sizes (12 variants per image) **synchronously** in
the request thread:

```python
for idx, raw_url in enumerate(merged):
    m = await asyncio.to_thread(variants_from_data_url, raw_url)
```

With 24 photos × ~1 s per Pillow encode = **20-40 s of submit latency**
spent staring at a spinner. Mobile.bg import had the same loop plus the
focus.bg fetch + optimize_many, totaling ~30-60 s.

### Fix
- Submit (`/auctions` POST): keeps the inline JPG + thumbnail
  generation (5 s for 24 images — that's the price of giving the
  buyer SOMETHING immediately) but **removes the sync variants loop**.
  Variants now generate in the background via
  `image_optimization_queue.enqueue_for_stored_urls()`, called right
  after `db.auctions.insert_one(doc)`.
- Mobile.bg import: same approach — deletes the inline
  `variants_from_data_url` loop. The importer doesn't enqueue (we don't
  know yet which images the seller will keep on the form) — that
  happens at submit time.
- Also parallelized the two `store_images` calls in submit via
  `asyncio.gather` — independent disk I/O.

### New helper (`services/image_optimization_queue.py`)
`enqueue_for_stored_urls(urls, auction_id, categories)`:
  • Parses each public URL to extract the content-addressed sha and
    locate the file on disk.
  • Falls back to SHA-hashing the file bytes if the URL isn't sha-
    addressed (defensive — should never trigger with the current
    storage backend).
  • Submits one job to the queue per image.

### Measured impact (self-benchmarks)
  | Scenario                          | Before     | After   | Δ      |
  | --------------------------------- | ---------- | ------- | ------ |
  | 12 imgs (1920×1080) submit        | ~15-20 s   | 1.92 s  | ~10×   |
  | 24 imgs (2400×1600) submit        | ~30-60 s   | 5.51 s  | ~10×   |
  | mobile.bg import (24 imgs)        | ~30-90 s   | 13.27 s | ~5×    |

Background queue catches up within ~30 s of submit; the responsive
`<Picture>` element on the frontend gracefully falls back to JPG URLs
in `images[]` until the manifest lands.

### Files touched
- `/app/backend/server.py` — create_auction, import_from_mobile_bg
- `/app/backend/services/image_optimization_queue.py` — new helper

### Verification
- `testing_agent_v3_fork` iteration 23: **21/21 backend tests passed,
  0 critical/minor issues.** Performance notes captured.
- Self-benchmarks above prove the speed-up.

### Rate limits (unchanged — they aren't the bottleneck)
  | Endpoint                          | Limit       | Comment                  |
  | --------------------------------- | ----------- | ------------------------ |
  | POST /api/auctions                | 10/minute   | reasonable for human use |
  | POST /api/auctions/import-mobile-bg | 10/minute | reasonable for human use |
  | POST /api/sell/image-upload       | 60/minute   | individual photos        |



### Bug
`roles/common/tasks/main.yml` had `PermitRootLogin no`. Every `site.yml`
run rewrote the live `/etc/ssh/sshd_config` back to that and restarted
sshd → `ssh root@…` and backend jump access were broken on every deploy.
Manual server fixes were silently undone the next deploy. Operator's
manual YAML edit corrupted formatting on top, blocking deploys entirely.

### Fix
Rewrote the sshd hardening section (`roles/common/tasks/main.yml`):

  • `PermitRootLogin prohibit-password` — root SSH allowed via key only,
    NEVER via password. Stronger than plain `yes` (which alone wouldn't
    forbid password fallback if `PasswordAuthentication` were ever
    toggled back on by some other tool).
  • `PubkeyAuthentication yes` — explicit, never leave to default.
  • `PasswordAuthentication no` — passwords disabled for every user.

Each task uses `validate: 'sshd -t -f %s'` so any malformed edit is
rolled back before sshd would refuse to start.

### Anti-regression
Ubuntu 24.04 cloud-init drops `/etc/ssh/sshd_config.d/50-cloud-init.conf`
with `PasswordAuthentication yes`, which is loaded AFTER the main file
and SILENTLY overrides our edits there. The role now greps every
`*.conf` snippet under `sshd_config.d/` for any conflicting directive
and rewrites it to match our policy. So the next time cloud-init drops
a snippet, the next `site.yml` will catch and override it.

### Files touched
- `/app/deploy/hetzner/ansible/roles/common/tasks/main.yml`

### Verification
- `python3 -c "yaml.safe_load_all(open(...))"` → all 21 tasks parse cleanly.
- Handler `restart sshd` exists and is referenced via `notify:`.

### Required user action (production)
Re-run `ansible-playbook -i ansible/inventory.ini playbooks/site.yml`
on both hosts. After it completes:
  • `ssh root@178.105.37.1 -i ~/.ssh/your_key` → works
  • `ssh root@178.105.37.1` (password) → refused (correct)
  • `ssh deploy@178.105.37.1 -i ~/.ssh/your_key` → works



### Root cause of production CDN 301 — DEPLOY PLAYBOOK BUG
Investigated why `/etc/nginx/sites-available/autoandbid` on production
contained ZERO `img.autoandbid.bg` config even though the repo file
(`deploy/hetzner/nginx/autoandbid.conf`) clearly has the dedicated vhost.

The bug: `deploy_frontend.yml` (the routine code-only redeploy) only
runs `nginx -s reload` — it NEVER copies `nginx/autoandbid.conf` from
the repo to `/etc/nginx/sites-available/autoandbid`. The nginx-config
tasks (Copy → Audit → Smoke-test) live only in `roles/frontend/tasks/
main.yml`, which runs ONLY via `site.yml` (the bootstrap-only playbook).

So once the routine deploy workflow was adopted (`deploy_frontend.yml`),
any change to `nginx/autoandbid.conf` was silently ignored, including
the entire `img.autoandbid.bg` server block added weeks ago. nginx kept
running the stale config → `img.autoandbid.bg` traffic was caught by
the main vhost → `301 → autoandbid.com/...` → text/html → Chrome ORB
blocked the images → import flows failed.

### Fix applied to `deploy/hetzner/ansible/playbooks/deploy_frontend.yml`
Added FIVE tasks after the build swap:
  1. **Refresh nginx config** — `force: yes` copy of `nginx/autoandbid.conf`
     → `/etc/nginx/sites-available/autoandbid`. Always overwrites.
  2. **Audit deployed file** — greps for `server_name img.autoandbid.bg;`
     AND `proxy_pass http://.../uploads/`. Fails the deploy IMMEDIATELY
     if either is missing (so a bad merge can't slip through).
  3. **Re-symlink** sites-enabled/autoandbid + remove default + remove
     any other competing site-config symlinks.
  4. **`nginx -t`** validation before reload.
  5. **Origin smoke test** — `curl -H 'Host: img.autoandbid.bg' https://127.0.0.1/`
     verifying root returns 4xx (not a redirect to autoandbid.com) and
     a missing /uploads/ asset returns 404 (not 301). FAILS the deploy
     on a cross-domain redirect.

Documented in README.md so operators know the routine playbook is
nginx-aware now.

### Frontend — client-side blob preview with blur while uploading
`ImageUploader.jsx`:
  - On file pick, `URL.createObjectURL(file)` gives an instant local
    preview — the photo is on the tile before the first XHR byte goes
    out. `blur-sm scale-105 brightness-95` differentiates "still
    uploading" from "saved".
  - On error: drop the blur so the user can clearly see WHICH photo
    failed; "Премахни" pill revokes the blob and clears the tile.
  - On success: revoke the blob URL before deleting from state so the
    File object isn't held by the browser one render longer than needed.
  - Translucent overlay + percent counter + spinner sit on top of the
    preview without obscuring it.
  - Final progress bar at the bottom, animated.

### Files touched
- `/app/deploy/hetzner/ansible/playbooks/deploy_frontend.yml` (rewritten)
- `/app/deploy/hetzner/README.md` (added warning callout)
- `/app/frontend/src/components/ImageUploader.jsx` (blob preview tiles)

### Verification
- `testing_agent_v3_fork` ran iteration 22: **20/20 backend tests passed,
  all frontend behaviour verified via Playwright. CDN probe confirmed
  production wrong_redirect=true.**

### Outstanding user action
- **Run `ansible-playbook -i ansible/inventory.ini playbooks/deploy_frontend.yml`
  on production.** The new tasks will:
    * Copy the (correct) nginx config over the (stale) deployed one
    * Fail the deploy if it lacks the CDN vhost (catches bad merges)
    * Smoke-test img.autoandbid.bg from inside the box
  After it succeeds, the production 301 will be GONE.



### Backend — async image optimization queue
- New module `/app/backend/services/image_optimization_queue.py`:
  - Single-worker asyncio queue (`MAX_CONCURRENCY=1`, CPU-bound work).
  - 3 attempts with exponential backoff `(5s, 30s, 120s)`.
  - 60s hard timeout per encode → never hangs the worker.
  - Resumes pending jobs on startup via `resume_pending()`.
  - Per-image status tracked in `auction.image_optimization.<sha>`:
    `optimizing` → `optimized` / `failed` with `attempts` + `last_error`.
  - DB stats aggregation + failed-items list for admin UI.
- New endpoints (`server.py`):
  - `POST /api/sell/image-upload` — multipart upload, 5 MB cap per file.
    Validates magic bytes (JPG/PNG/WebP). Persists ORIGINAL to disk
    content-addressed (`auctions/<aa>/<sha>.<ext>`), enqueues variant
    generation, returns public URL + sha + status. Originals are NEVER
    deleted — variants augment them.
  - `GET /api/images/status?shas=...` — poll endpoint for the frontend
    to swap original `<img>` for `<picture>` with AVIF variants once
    the worker has produced them.
  - `GET /api/admin/image-queue` — live + persistent queue stats +
    list of auctions with failed optimizations.
  - `POST /api/admin/image-queue/retry` — re-enqueue a failed image.
  - `GET /api/admin/cdn-health` — live diagnostic that probes
    `img.autoandbid.bg` via Cloudflare AND (optionally) directly to
    origin IP (set `CDN_ORIGIN_IP` env). Reports `wrong_redirect: true`
    when CF returns a 301 to a different host — the production failure
    mode that broke listing photos for 2 days.

### Frontend
- `ImageUploader.jsx` rewritten:
  - REMOVED `browser-image-compression` package (was unused) and all
    client-side `encodeAtQuality` + `compress` logic.
  - Sends ORIGINAL files via multipart `FormData` to `/api/sell/image-upload`.
  - Per-file progress bar via XHR `onprogress` events.
  - Failed uploads stay visible with an inline error pill + dismiss.
  - HEIC → JPEG conversion kept (Safari-only would-be users + libheif WASM
    lazy-loaded).
  - 5 MB per-file cap matches backend exactly.
- `AdminHealthTab.jsx` extended with two new sections:
  - **Image optimization queue** — 6 stat cards + failed-images list with
    inline retry buttons.
  - **CDN probe** — manual `Пусни probe` button hits `/admin/cdn-health`
    and renders two side-by-side cards (CF path vs origin path) with a
    diagnosis verdict.

### CDN 301 root cause IDENTIFIED via the new endpoint
Live probe through preview env confirmed:
```
cf_path.status      = 301
cf_path.location    = https://autoandbid.com/uploads/__probe__.jpg
cf_path.content_type= text/html
cf_path.server      = cloudflare
cf_path.wrong_redirect = TRUE
```
The `server: cloudflare` header + `cf-ray` proves the 301 is INJECTED by
Cloudflare BEFORE the request hits origin nginx. Origin probe (which
requires `CDN_ORIGIN_IP` env) will confirm origin is fine.

### Files touched
- `/app/backend/services/image_optimization_queue.py` (new)
- `/app/backend/server.py` (new endpoints + startup hook)
- `/app/frontend/src/components/ImageUploader.jsx`
- `/app/frontend/src/components/AdminHealthTab.jsx`
- `/app/frontend/package.json` (-`browser-image-compression`)

### Verification
- `POST /api/sell/image-upload` returns 200 with URL + sha + status.
- Worker encodes variants for a real 300×200 JPEG → manifest with
  thumb/card/gallery/full × AVIF/WebP/JPG present in
  `auction.image_optimization.<sha>.manifest`.
- `/api/admin/image-queue` shows `optimized: 1` after encode.
- `/api/admin/cdn-health` correctly identifies `wrong_redirect: true`
  against production `img.autoandbid.bg`.

### Outstanding follow-ups (next iteration)
- Frontend `<picture>` element wiring in `AuctionDetailPage` / car cards
  to consume AVIF variants from the manifest (today still shows the JPEG
  original — works, but doesn't yet benefit from 40% smaller AVIF).
- Set `CDN_ORIGIN_IP` env on production backend so the CDN probe can
  bypass Cloudflare and definitively prove origin is healthy.
- User action required on production Cloudflare dashboard: inspect
  Page Rules / Bulk Redirects / Workers filtering on `img.autoandbid.bg`.



### Frontend
- **Passkey reauth input focus loss FIXED** — `PasskeySection.jsx`. Преди:
  `<ReauthGate />` беше дефиниран ВЪТРЕ в функционалния компонент → на
  всеки render React виждаше нов component identity и unmount-ваше
  `<input>` → фокусът се губеше след 1 символ. След: JSX е inline в
  основния return (canonical React fix).
- **AccountSettingsPage runtime crash FIXED** — `smsOpt is not defined`
  ReferenceError след premахването на SMS опции в предишната итерация.
  Cекцията е преобразувана в чисто "Телефон за контакт" поле (телефонът
  все още се пази за фактуриране / KYC, без SMS opt-in).

### Backend — WebAuthn multi-domain (passkey.py)
- `rp_id` сега е **динамичен per request** — извлича се от `Origin`
  header (`autoandbid.bg` / `.com` / `.ro`), вместо да е hardcoded на
  `.bg`. www.* се мапва към apex. Preview / dev hostnames използват
  env `WEBAUTHN_RP_ID` като fallback.
- Всеки credential съхранява `rp_id_when_created`; verification ползва
  точно него → пасiquetите enrolled-нати на `.ro` работят на `.ro`,
  тези на `.bg` работят на `.bg`. Това е правилният WebAuthn модел и
  единственият, който е надежден на всички съвременни браузъри
  (Chromium / Safari / Firefox), за разлика от Related Origin Requests
  manifest, който е counterintuitively unreliable на `.ro` / Safari.
- `_allowed_origins_for_rp()` ограничава `expected_origin` до apex + www
  на конкретния brand при verification — допълнителна защита.

### Files touched
- `/app/frontend/src/components/PasskeySection.jsx`
- `/app/frontend/src/pages/AccountSettingsPage.jsx`
- `/app/backend/routers/passkey.py`

### Verification
- curl test: 4/4 brand origins (bg/com/ro/www.ro) връщат правилен `rpId`.
- Playwright test: 8 символа въведени в passkey reauth input → фокусът
  остава върху същия `<input>`, value е пълен. PASS.
- Settings page рендерира без runtime errors.

### Outstanding (NOT in this iteration)
- **Production CDN 301** (`img.autoandbid.bg`) — Ansible deploy role
  вече FAILS с smoke test при тази грешка (виж
  `deploy/hetzner/ansible/roles/frontend/tasks/main.yml`, "CDN smoke
  test"). Ако 301 persist-ва **след** успешен `ansible-playbook`, тогава
  източникът е Cloudflare (Page Rule / Bulk Redirect / orange-cloud на
  CNAME сочещ грешен origin), НЕ origin nginx. Debug стъпки:
    1. `curl -sk -D - --resolve img.autoandbid.bg:443:$(dig +short ab-front1) https://img.autoandbid.bg/uploads/foo.jpg`
       (заобикаля Cloudflare — ако върне 404 image/jpeg → origin OK).
    2. `curl -sk -D - https://img.autoandbid.bg/uploads/foo.jpg`
       (минава през CF — ако върне 301 → CF проблем).
    3. В Cloudflare → Rules → Page Rules + Bulk Redirects:
       търси правило с pattern съдържащ `img.autoandbid.bg` или
       `*autoandbid.bg/*`.
    4. DNS: `img.autoandbid.bg` трябва да е CNAME към `ab-front1`
       или A към публичния IP, **не** към `autoandbid.bg`.


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


## 2026-05-12 — Iteration 21: CDN env rename + image categorization + lazy-load card slides

### Backend
- `services/image_variants.py public_variant_url` сега резолва env vars в реда: `IMAGE_BASE_URL` → legacy `IMAGE_CDN_BASE` → relative `/api/uploads/`. `IMAGE_BASE_URL` е canonical име за production setup `img.autoandbid.bg` зад frontend nginx reverse proxy.
- Submit handler (`POST /api/auctions`) изгражда `image_categories[]` paralел с `merged[]`: първа exterior снимка = `main`, останалите exterior = `exterior`, bumper/wheels = `detail`, interior = `interior`. Uncategorized payload → първата = `main`, останалите = `other`.
- mobile.bg import: первата снимка = `main`, останалите = `exterior` (heuristic — листингите не носят category metadata).
- `CachedStaticFiles` subclass на `/api/uploads` mount: `variants/*` → `Cache-Control: public, max-age=31536000, immutable`; всичко друго → `max-age=604800`. Cloudflare в preview env override-ва, в production headers стигат до клиента.

### Frontend
- `AuctionCard.jsx`:
  - Нова `pickOrderedPreviewSlides(variants, legacyImages)` функция: подрежда 4 preview slides в реда **main → exterior → interior × 2 → filler**. Graceful fallback за legacy auctions без categories.
  - Lazy-load gating: само първият slide рендерира `<Picture priority>`. Slides 2-4 показват placeholder div, докато потребителят не направи `pointerdown` / `touchstart` / `mouseenter` на картата → `primed=true` → всички slides се рендерират.
  - CTA slide ("View full auction") винаги е visible — 5-ти slide, акцентен dot.

### Infrastructure docs
- **Production setup**: 
  - DNS `img.autoandbid.bg` → frontend server public IP
  - nginx vhost на frontend: `proxy_pass http://<private-backend>:8001/api/uploads/variants/` с `proxy_cache` enabled
  - Backend: `IMAGE_BASE_URL=https://img.autoandbid.bg` в .env
  - Cache headers travel through end-to-end; CDN (Cloudflare/Bunny) може да се сложи отгоре без code промени.

### Tested
- testing_agent_v3_fork (iteration_21.json) — 20/21 backend ✅ (1 skipped), 100% frontend ✅, 0 issues, 0 action items.
- Lazy-load verified: 1 `<picture>` + 3 placeholder divs преди hover → 4 `<picture>` след hover. Slide ordering main→exterior→interior×2 verified чрез seeded auction.

