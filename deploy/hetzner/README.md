## Hetzner Deployment — autoandbid

Three brand domains, one React build, two machines:

```
                  Internet
        ┌────────────┴────────────┐
        ▼            ▼            ▼
  autoandbid.com  .bg   .ro     ← Cloudflare zones (one per TLD)
        └────────────┬────────────┘
                proxied → 178.105.37.1
                     │
                     ▼
   ┌───────────────────────────────────┐
   │  ab-front1   public  178.105.37.1 │
   │              private 10.0.0.2     │
   │  • nginx (80/443)                 │
   │  • React build /var/www/autobids  │
   │  • language auto-detected by host │
   │  • proxy /api → ab-back1:8001     │
   └───────────────┬───────────────────┘
                   │  private network
                   ▼
   ┌───────────────────────────────────┐
   │  ab-back1    private 10.0.0.3     │
   │  • FastAPI uvicorn :8001          │
   │  • MongoDB localhost:27017        │
   │  • PostgreSQL localhost:5432      │
   └───────────────────────────────────┘
```

**Language by domain (single bundle, runtime decision):**
- `autoandbid.com` → English (international default)
- `autoandbid.bg`  → Bulgarian
- `autoandbid.ro`  → Romanian

> 📘 **First time deploying?** Read `INITIAL_DEPLOY.md` end-to-end before running anything. The condensed reference below assumes you know what you're doing.

> ⚙️ **What changed since first deploy** — see the
> "Production Quirks & Permanent Fixes" section at the bottom of
> `INITIAL_DEPLOY.md`. Highlights:
> - Backend uses system `python3` (not deadsnakes 3.11)
> - MongoDB apt repo pinned to `jammy` on Noble
> - `POSTGRES_URL` requires `+asyncpg` driver prefix
> - `emergentintegrations` removed → direct Gemini SDK for translations
> - uvicorn binds `0.0.0.0:8001` (private LAN only)
> - `yarn build` runs with `CI=false`
> - SSH hardening only after deploy key install (lockout-proof)
> - `backend.env` and `.env.production` are **never** clobbered on rerun
> - `REACT_APP_BACKEND_URL` is **EMPTY** in production — same-origin /api/*



### Layout

```
deploy/hetzner/
├── ansible/
│   ├── ansible.cfg
│   ├── inventory.ini                    ← machine list (use private IPs internally)
│   ├── group_vars/
│   │   └── all.yml                      ← non-secret defaults
│   ├── roles/
│   │   ├── common/                      ← OS hardening shared by both nodes
│   │   ├── backend/                     ← FastAPI + Mongo + Postgres on ab-back1
│   │   └── frontend/                    ← nginx + static build on ab-front1
│   └── playbooks/
│       ├── bootstrap.yml                ← run once on a fresh machine
│       ├── deploy_backend.yml           ← code-only redeploy (idempotent)
│       ├── deploy_frontend.yml          ← code-only redeploy (idempotent)
│       └── site.yml                     ← full setup (bootstrap + deploys)
├── nginx/
│   └── autoandbid.conf                  ← reverse proxy + static SPA
├── systemd/
│   └── autobids-backend.service         ← uvicorn under www-data
├── env-templates/
│   ├── backend.env.example
│   └── frontend.env.production.example
└── README.md  ← (this file)
```

---

## 1. One-time prerequisites on your laptop

```bash
# macOS (brew) or Debian/Ubuntu
sudo apt-get install -y ansible || brew install ansible

# Install required ansible collections (community.general, ansible.posix)
ansible-galaxy collection install -r ansible/requirements.yml

# Clone the repo and cd into the deploy dir
cd /path/to/autobids/deploy/hetzner

# SSH config — jump host so private-IP'd ab-back1 is reachable
cat >> ~/.ssh/config <<'EOF'
Host ab-front1
  HostName 178.105.37.1
  User deploy
  IdentityFile ~/.ssh/hetzner_ed25519

Host ab-back1
  HostName 10.0.0.3
  User deploy
  IdentityFile ~/.ssh/hetzner_ed25519
  ProxyJump ab-front1
EOF

# Quick connectivity check
ssh ab-front1 'hostname'
ssh ab-back1  'hostname'
```

> **Tip:** if you only have `root@178.105.37.1` access at first, run `ansible-playbook playbooks/bootstrap.yml -u root --ask-pass` once — it creates the `deploy` user and disables root SSH login.

---

## 2. Configure secrets

Copy the example env files and fill them with **production** values:

```bash
cp env-templates/backend.env.example                      ansible/files/backend.env
cp env-templates/frontend.env.production.example          ansible/files/frontend.env.production
chmod 600 ansible/files/*
```

> These two files are git-ignored. Never commit them.

---

## 3. Initial deploy (run once)

```bash
# Full setup: OS hardening, nginx, Mongo, Postgres, Python, build & start
ansible-playbook -i ansible/inventory.ini ansible/playbooks/site.yml
```

What the playbook does, in order:

| Step | On host | Role | Notes |
|---|---|---|---|
| 1 | both | `common` | unattended-upgrades, ufw, fail2ban, deploy user, hostnames in `/etc/hosts` |
| 2 | ab-back1 | `backend` | install Python 3.11, MongoDB 7, PostgreSQL 16, clone code, install deps, `.env`, systemd unit, start service |
| 3 | ab-front1 | `frontend` | install Node 20, build React, install nginx, deploy config, reload |

---

## 4. Subsequent deploys (code-only)

```bash
# Backend code change
ansible-playbook -i ansible/inventory.ini ansible/playbooks/deploy_backend.yml

# Frontend code change
ansible-playbook -i ansible/inventory.ini ansible/playbooks/deploy_frontend.yml
```

Both are **idempotent** — they pull the latest commit from the configured git ref, install deps, rebuild, and reload the service in-place.

---

## 5. Cloudflare configuration — three brand domains

**One Cloudflare zone per TLD** (you'll need to add `autoandbid.com`, `autoandbid.bg`, and `autoandbid.ro` separately as zones).

For **each** of the three zones, configure the same way:

### a. DNS records
| Type | Name | Content | Proxy | Notes |
|---|---|---|---|---|
| A | `@`   | `178.105.37.1` | 🟠 Proxied | Apex domain |
| A | `www` | `178.105.37.1` | 🟠 Proxied | Optional — nginx redirects to apex |

So for `autoandbid.bg`:
- `A   autoandbid.bg       → 178.105.37.1   Proxied`
- `A   www.autoandbid.bg   → 178.105.37.1   Proxied`

…and identical entries for `.com` and `.ro`.

### b. SSL/TLS
- **Mode**: Full (Strict) on all three zones.
- **Origin Certificate**: generate ONE cert covering all three apex+wildcard SANs:
  ```
  autoandbid.com  *.autoandbid.com
  autoandbid.bg   *.autoandbid.bg
  autoandbid.ro   *.autoandbid.ro
  ```
  Save to `ab-front1` as:
  - `/etc/ssl/autoandbid/cert.pem` (chain: cert + Cloudflare CA)
  - `/etc/ssl/autoandbid/key.pem`  (mode 600)

  > Cloudflare's Origin CA does not let you mix multiple bare TLDs in one cert — generate **one cert per zone** if needed (`cert.com.pem`, `cert.bg.pem`, `cert.ro.pem`) and split each into its own nginx server block. The supplied `nginx/autoandbid.conf` works with a single combined cert if your CA supports multi-domain (you can use Let's Encrypt + DNS-01 for that).

### c. Per-zone settings (apply on all three)
- **Always Use HTTPS**: ON
- **Automatic HTTPS Rewrites**: ON
- **Brotli**: ON
- **HSTS**: enable after you're confident (max-age 31536000, include subdomains)
- **Bot Fight Mode**: ON (free tier is fine to start)

### d. How language auto-detection works
- The frontend bundle reads `window.location.hostname` on every page load
- `autoandbid.com` → English (`en`) — international default
- `autoandbid.bg`  → Bulgarian (`bg`)
- `autoandbid.ro`  → Romanian (`ro`)
- Users can still switch language manually via the header; their choice persists in `localStorage` for that origin only.
- The mapping is configurable via `REACT_APP_DOMAIN_BG/RO/EN` in `frontend.env.production` (already set in the template).

---

## 6. Health checks

```bash
# Backend health (run from ab-front1 or your laptop)
curl -fsSL https://autoandbid.com/api/health           # { "status": "ok" }

# Service status
ssh ab-back1  'systemctl status autobids-backend'
ssh ab-front1 'systemctl status nginx'

# Tail backend logs
ssh ab-back1 'journalctl -fu autobids-backend'
```

---

## 7. Rollback

`deploy_backend.yml` keeps the previous release in `/opt/autobids-backend.previous`. To roll back:

```bash
ssh ab-back1 'sudo /opt/autobids/scripts/rollback.sh'   # symlink swap + service restart
```

---

## Notes

- **No Docker** — services run under systemd directly (lower memory, faster cold start, easier to debug).
- **Secrets** live in `/etc/autobids/backend.env` (mode 600, owned by `www-data`). Never echoed to logs.
- **Hot-reload off** in production. Backend is a single uvicorn worker by default; bump `WORKERS=` in the env to scale up.
- **Backups**: `mongodump` + `pg_dump` cron is set up by the `backend` role (writes to `/var/backups/autobids/`).
