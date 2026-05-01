# Initial Hetzner Deploy — Step-by-step

This is the first-time deploy walkthrough. After this completes, use
`deploy_backend.yml` / `deploy_frontend.yml` for all subsequent updates.

> **Read this end-to-end before running anything.** Each step assumes the previous one finished cleanly.

---

## Phase 0 — Pre-flight (15 min)

### 0.1 Local prerequisites

```bash
# Pick whichever applies to your laptop
sudo apt-get install -y ansible openssh-client rsync
# or:
brew install ansible

ansible --version              # >= 2.15
ansible-galaxy collection install -r ansible/requirements.yml
```

### 0.2 SSH access

You should already have:
- SSH key on `krassi-ampere` (= `ab-front1`) → public IP `178.105.37.1`
- Generated a SSH key on `ab-front1` whose public part is on `krassi-ampere2` (= `ab-back1`)
- Both machines reachable as `ssh root@178.105.37.1` (initially) or via the deploy user (after bootstrap).

Add this to `~/.ssh/config` on your laptop:

```
Host ab-front1
  HostName 178.105.37.1
  User deploy
  IdentityFile ~/.ssh/hetzner_ed25519

Host ab-back1
  HostName 10.0.0.3
  User deploy
  IdentityFile ~/.ssh/hetzner_ed25519
  ProxyJump ab-front1
```

Quick sanity:
```bash
ssh ab-front1 'hostname && cat /etc/hosts'
ssh ab-back1  'hostname && cat /etc/hosts'
```

If you only have `root` access right now, that's fine — keep going. The bootstrap step creates the `deploy` user.

---

## Phase 1 — Fill the env templates (20 min)

```bash
cd deploy/hetzner

# Backend secrets
cp env-templates/backend.env.example                  ansible/files/backend.env
cp env-templates/frontend.env.production.example      ansible/files/frontend.env.production
chmod 600 ansible/files/backend.env ansible/files/frontend.env.production

# Open them in your editor and fill every CHANGE_ME
$EDITOR ansible/files/backend.env
$EDITOR ansible/files/frontend.env.production
```

### What you need before continuing
| Variable | Where to get it |
|---|---|
| `JWT_SECRET` | `openssl rand -hex 32` |
| `STRIPE_API_KEY` | https://dashboard.stripe.com/apikeys (use **live** key) |
| `STRIPE_WEBHOOK_SECRET` | Create webhook at https://dashboard.stripe.com/webhooks pointing to `https://autoandbid.com/api/stripe/webhook`; copy the signing secret. |
| `RESEND_API_KEY` | https://resend.com/api-keys |
| `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` | https://console.twilio.com/ |
| `TWILIO_FROM_NUMBER` | Your purchased Twilio number, E.164 format |
| `VAPID_PUBLIC_KEY` / `VAPID_PRIVATE_KEY` | `npx web-push generate-vapid-keys` |
| `GEMINI_API_KEY` | https://aistudio.google.com/apikey (free tier) |
| `POSTGRES_URL` | After bootstrap you'll set this; default `postgresql://autobids:STRONG_PASS@localhost:5432/autobids` |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | First-time admin seed (Argon2id will hash on first start) |

> **Don't commit these files** — they're already in `.gitignore`.

---

## Phase 2 — Edit the inventory and group_vars (5 min)

```bash
$EDITOR ansible/inventory.ini       # only the IP/SSH user — already correct if your network matches
$EDITOR ansible/group_vars/all.yml  # CHANGE `repo_url` to your actual GitHub repo URL
```

The two values you'll definitely change:
- `repo_url` in `group_vars/all.yml` (it currently says `git@github.com:YOUR_ORG/autobids.git`)
- `repo_branch` if you don't want `main`

---

## Phase 3 — Bootstrap the OS (10 min, one-time)

If your machines were just created with root SSH only:

```bash
# Use root explicitly for the very first run
ansible-playbook -i ansible/inventory.ini ansible/playbooks/bootstrap.yml \
    -u root --ask-pass
```

After this completes:
- `deploy` user exists with sudo + your SSH key
- Root SSH login is disabled
- UFW + fail2ban are running
- `/etc/hosts` knows `ab-front1`, `ab-back1`, `ab-db1`, `ab-deploy`

From now on, **never use `-u root`** — the `deploy` user is the only way in.

---

## Phase 4 — Database password (PostgreSQL only, 2 min)

PostgreSQL is installed by the backend role, but you need to set its password
manually before the FastAPI app can connect. SSH into ab-back1:

```bash
ssh ab-back1
sudo -u postgres psql <<EOF
CREATE USER autobids WITH PASSWORD 'STRONG_PASS_HERE';
CREATE DATABASE autobids OWNER autobids;
GRANT ALL PRIVILEGES ON DATABASE autobids TO autobids;
EOF
exit
```

Update the matching value in `ansible/files/backend.env`:
```
POSTGRES_URL=postgresql://autobids:STRONG_PASS_HERE@localhost:5432/autobids
```

> **Order matters**: do this AFTER `site.yml` finishes (PostgreSQL only exists after that runs). Then re-run `deploy_backend.yml` to push the updated env and restart.

---

## Phase 5 — Full setup (20–30 min)

```bash
ansible-playbook -i ansible/inventory.ini ansible/playbooks/site.yml
```

Watch for `failed=` at the end. If anything is non-zero:
- Re-run; tasks are idempotent.
- If the same task keeps failing, check the error and `journalctl` on the affected machine.

**What this does:**
1. Hardens both machines (`common` role)
2. On `ab-back1`: installs Python 3.11, MongoDB 7, PostgreSQL 16, clones the repo, creates a venv, installs deps, drops `backend.env`, installs and starts the systemd service, sets up nightly backups
3. On `ab-front1`: installs Node 20, runs `yarn build`, syncs to `/var/www/autobids/build`, installs nginx, deploys the multi-domain config, reloads nginx

---

## Phase 6 — Cloudflare DNS + TLS (15 min)

**Three Cloudflare zones**, one per TLD. For each:

1. Create the zone, copy the assigned NS records to your domain registrar
2. Wait for `Status: Active`
3. Add DNS records (apex + www both → `178.105.37.1`, both Proxied)
4. SSL/TLS mode = Full (Strict)

### Origin Certificate

In Cloudflare → SSL/TLS → Origin Server → Create Certificate. Per zone, list:
- `autoandbid.com  *.autoandbid.com`   (zone .com)
- `autoandbid.bg   *.autoandbid.bg`    (zone .bg)
- `autoandbid.ro   *.autoandbid.ro`    (zone .ro)

> Cloudflare's Origin CA accepts only one apex per cert, so you'll generate **three certs** and concatenate them, OR use Let's Encrypt with DNS-01 to get one cert covering all three. Both approaches work; pick what's simpler for you.

If you go with three certs, copy each to ab-front1:
```bash
scp cert.com.pem ab-front1:/tmp/
scp key.com.pem  ab-front1:/tmp/
ssh ab-front1
sudo mkdir -p /etc/ssl/autoandbid
# Concatenate: cat cert.com.pem cert.bg.pem cert.ro.pem > /etc/ssl/autoandbid/cert.pem
# Concatenate: cat key.com.pem  key.bg.pem  key.ro.pem  > /etc/ssl/autoandbid/key.pem
sudo chmod 600 /etc/ssl/autoandbid/key.pem
sudo nginx -t && sudo systemctl reload nginx
```

---

## Phase 7 — Smoke tests

```bash
# Backend health (from your laptop, going through Cloudflare)
curl -fsSL https://autoandbid.com/api/health
curl -fsSL https://autoandbid.bg/api/health
curl -fsSL https://autoandbid.ro/api/health
# All three should return: {"status":"ok"}

# Language auto-detect
curl -s https://autoandbid.com  | grep -o '"lang":"[a-z]*"' | head -1   # → "en"
curl -s https://autoandbid.bg   | grep -o '"lang":"[a-z]*"' | head -1   # → "bg"
curl -s https://autoandbid.ro   | grep -o '"lang":"[a-z]*"' | head -1   # → "ro"

# Service status from inside the network
ssh ab-back1  'systemctl status autobids-backend --no-pager | head -20'
ssh ab-front1 'systemctl status nginx              --no-pager | head -20'

# Tail backend logs while you click through the live site
ssh ab-back1 'journalctl -fu autobids-backend'
```

---

## Phase 8 — Stripe webhook verification

After the public site is up, configure the Stripe webhook:

1. https://dashboard.stripe.com/webhooks → Add endpoint
2. URL: `https://autoandbid.com/api/stripe/webhook`
3. Events: `checkout.session.completed`, `payment_intent.succeeded`, `payment_intent.payment_failed`, `setup_intent.succeeded`
4. Copy the signing secret (starts `whsec_…`)
5. Update `ansible/files/backend.env` → `STRIPE_WEBHOOK_SECRET=...`
6. Redeploy backend so the new env is loaded:

```bash
ansible-playbook -i ansible/inventory.ini ansible/playbooks/deploy_backend.yml
```

7. In Stripe dashboard → click "Send test webhook" → verify it appears in `journalctl -fu autobids-backend` and the response is 200.

---

## Phase 9 — Lock down (optional but recommended)

Once everything works:
- Enable HSTS in Cloudflare (per zone) — careful, hard to undo
- Set up monitoring: UptimeRobot or Better Stack on `https://autoandbid.com/api/health` (free tier is fine for one endpoint)
- Schedule backup verification: monthly cron on your laptop that downloads the latest `mongo-*.gz` from `/var/backups/autobids/` and runs `mongorestore --dry-run`

---

## Trouble?

| Symptom | Likely cause | Fix |
|---|---|---|
| `502 Bad Gateway` from nginx | Backend service not running | `ssh ab-back1 'systemctl status autobids-backend'` and check logs |
| `Permission denied (publickey)` | Wrong SSH key or `deploy` user not yet created | Re-run bootstrap with `-u root --ask-pass` |
| `502` on `/api/stripe/webhook` only | Webhook signing secret mismatch | Copy the **current** secret from Stripe → update env → redeploy |
| Frontend shows old version | Browser cached `index.html` | Hard refresh (Cmd-Shift-R) — service worker auto-updates within 60s |
| Wrong language on `.bg` | DNS not yet propagated, or `REACT_APP_DOMAIN_BG` mismatch | `dig autoandbid.bg` + verify `frontend.env.production` baked correct values |

For everything else: tail `journalctl -fu autobids-backend` while reproducing the issue. The app logs structured errors with stack traces.


---

## Production Quirks & Permanent Fixes (applied May 2026)

These are quirks we hit during the first production deploy onto Ubuntu 24.04
(Noble) Hetzner boxes. **All of them are already baked into the Ansible
playbooks / env templates / systemd units in this repo** — the section is
here so future operators know *why* the code looks the way it does and what
to expect on a fresh box.

### Python / venv
- The backend role uses the **system default `python3`** (3.12 on Noble,
  3.11 on Jammy). The `deadsnakes` PPA step was removed — it timed out on
  Hetzner and is unnecessary for this codebase.
- `group_vars/all.yml :: python_version` is now `"3.12"` — informational only.

### PostgreSQL async driver
- `POSTGRES_URL` **must** begin with `postgresql+asyncpg://` (not plain
  `postgresql://`). `backend.env.example` and all docs now reflect this.
- `asyncpg==0.31.0` is pinned in `backend/requirements.txt`. `psycopg2-binary`
  is **not** required at runtime — only the Ansible `postgresql_*` modules
  need `python3-psycopg2`, which is installed via apt, not pip.

### MongoDB 7 on Noble
- MongoDB 7.0 has no `noble/mongodb-org/7.0` apt channel yet. The backend
  role pins to `jammy` — works fine on Noble. Revisit this once MongoDB
  publishes a Noble build.

### Emergent-only dependency removed
- `emergentintegrations==0.1.0` has been deleted from `requirements.txt` —
  it only installs from Emergent's private index.
- `backend/translate.py` is **provider-hybrid** so the same code works in
  both environments:
  - **Production (Hetzner)** → set `GEMINI_API_KEY` in
    `/etc/autobids/backend.env`. Uses the direct `google-generativeai`
    SDK (already in requirements). Free tier:
    https://aistudio.google.com/apikey.
  - **Emergent preview** → falls back to `EMERGENT_LLM_KEY` +
    `emergentintegrations` (only installable inside the Emergent pod).
  - If neither is set, `translate_text()` returns `None` and the
    frontend shows the Bulgarian original with a small
    "AI translation temporarily unavailable" notice — app keeps working.
- **Migration on Hetzner**: if you forgot to set `GEMINI_API_KEY`, users
  will see the Bulgarian text on `.com` / `.ro`. Set the key, restart
  `autobids-backend`, done — translations repopulate lazily on first view
  and cache per auction document.

### uvicorn listens on 0.0.0.0
- The systemd unit binds uvicorn to `0.0.0.0:8001` (not 127.0.0.1). Nginx on
  ab-front1 reaches the backend over the private LAN (`10.0.0.3:8001`). UFW
  keeps 8001 open only to `10.0.0.0/16` — the port is NOT exposed to the
  public internet.

### Frontend build — CI=false
- `yarn build` runs with `CI=false`. CRA treats every ESLint warning as a
  fatal error under CI=true, which used to break prod over cosmetic lint
  issues. Errors are still caught by the bundler; only warnings are demoted.

### SSH safety
- The `common` role now installs the deploy user's public key **before**
  running `PermitRootLogin no`. An `assert` guards against running the
  hardening step with no deploy key configured, so a misconfig can never
  lock us out again.
- Configure one of:
  - `group_vars/all.yml :: deploy_ssh_public_keys: ["ssh-ed25519 ..."]`, or
  - drop one key per line into `roles/common/files/deploy_authorized_keys`.
- Optional: `operator_ssh_sources: ["1.2.3.4/32", ...]` restricts UFW port
  22 to your operator IPs (default: `any`).

### Secrets are never clobbered
- `backend.env` and `frontend.env.production` are copied with `force: no`
  and a pre-check `stat` task. **A rerun of the full playbook will never
  overwrite a live production env file.** To rotate a secret, edit the
  file directly on the server and restart the service.
- Same contract for `/etc/ssl/autoandbid/{cert,key}.pem`. The frontend role
  creates the directory but never writes certs — drop your Cloudflare
  Origin cert in place manually (see Phase 4).

### App directory layout
- The backend role explicitly pre-creates `{{ app_dir }}/scripts` before
  writing `rollback.sh` — this used to fail on a fresh box where the
  directory had not been touched yet.

### Admin & email verification
- The seed admin (`ADMIN_EMAIL` / `ADMIN_PASSWORD`) is created on first boot
  with `role=admin`, `email_verified=true`. Admin / moderator roles are
  **always** exempt from the `require_verified_email` gate in the backend
  — they cannot be locked out of their own control panel by a verification
  bug.
- If you ever need to manually unlock an admin:
  ```js
  // mongosh
  use autobids
  db.users.updateOne(
    { email: "admin@autoandbid.com" },
    { $set: { email_verified: true, verification_required: false },
      $unset: { totp_enabled: "", totp_secret: "", totp_backup_codes: "",
                totp_confirmed_at: "", failed_login_attempts: "",
                locked_until: "" } }
  )
  ```

### Cloudflare + cookies
- The backend sets `COOKIE_SECURE=1`, `COOKIE_SAMESITE=lax` in production.
- `CORS_ORIGINS` / `ALLOWED_ORIGINS` in `backend.env` must list all six
  origin variants (apex + www × 3 TLDs) — already wired in the template.
- nginx uses `CF-Connecting-IP` for real client IPs; the Cloudflare IP
  range block in `nginx/autoandbid.conf` is authoritative.

### Hetzner firewall
- Public :80 / :443 should be restricted to Cloudflare IP ranges at the
  **Hetzner Cloud Firewall** layer (not just nginx/UFW). This is managed
  in the Hetzner Cloud panel — not in Ansible.
- SSH :22 should be restricted to your operator IPs using the same
  Hetzner firewall, or via `operator_ssh_sources` in group_vars.

### Push notifications — zero Emergent dependency
- Web Push uses `pywebpush` (VAPID keys) directly. Generate once:
  ```bash
  npx web-push generate-vapid-keys
  ```
  and store the pair in `backend.env` as `VAPID_PUBLIC_KEY` /
  `VAPID_PRIVATE_KEY`. No third-party account required.

### Transactional email — Resend
- `RESEND_API_KEY` is enough on its own. `SENDER_EMAIL` must be a verified
  sender on the Resend dashboard (usually `noreply@autoandbid.com` — add
  the suggested SPF/DKIM records in Cloudflare DNS for each zone).
- If the API key is empty, `send_email()` silently mocks and logs to
  `notification_log`. Users won't receive mail but the app keeps running.
