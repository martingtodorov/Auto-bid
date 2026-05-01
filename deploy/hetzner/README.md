## Hetzner Deployment — autoandbid.com

Two-machine architecture:

```
                Internet
                   │
                   ▼
            ┌──────────────┐
            │  Cloudflare  │  (DNS + DDoS shield)
            └──────┬───────┘
                   │  proxied → 178.105.37.1
                   ▼
   ┌───────────────────────────────────┐
   │  ab-front1   public  178.105.37.1 │
   │              private 10.0.0.2     │
   │  • nginx (80/443)                 │
   │  • React build /var/www/autobids  │
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

## 5. Cloudflare configuration

1. **DNS**:
   - `A   autoandbid.com   178.105.37.1`   (Proxied = 🟠)
   - `A   www              178.105.37.1`   (Proxied = 🟠)
2. **SSL/TLS mode**: Full (Strict) — generate an Origin Certificate in Cloudflare → SSL/TLS → Origin Server, copy to `/etc/ssl/autoandbid/cert.pem` + `key.pem` on `ab-front1`.
3. **Always Use HTTPS**: ON
4. **Automatic HTTPS Rewrites**: ON
5. **HSTS**: enable after you're confident the certs are stable (max-age 31536000, include subdomains)

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
