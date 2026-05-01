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
