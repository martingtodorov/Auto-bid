# Auto&Bid — Production Deployment Guide

End-to-end instructions for running Auto&Bid on **any managed VPS, container
platform or Kubernetes cluster** with zero dependency on Emergent-only runtime
features.

> **Prerequisites**: Docker ≥ 24, Docker Compose v2, a domain with DNS access.

## Contents

1. [Architecture at a glance](#1-architecture-at-a-glance)
2. [One-minute local preview](#2-one-minute-local-preview)
3. [Single-VPS deployment](#3-single-vps-deployment)
4. [Managed hosting options](#4-managed-hosting-options)
   * [Railway](#railway)
   * [Render](#render)
   * [DigitalOcean App Platform](#digitalocean-app-platform)
   * [Fly.io](#flyio)
5. [Object storage for uploads](#5-object-storage-for-uploads)
6. [Environment reference](#6-environment-reference)
7. [Secrets rotation & backups](#7-secrets-rotation--backups)
8. [Observability & logs](#8-observability--logs)
9. [Scaling playbook](#9-scaling-playbook)
10. [Future: PostgreSQL migration](#10-future-postgresql-migration)

---

## 1. Architecture at a glance

```
┌──────────────────────────────────────────────────────────────────┐
│  CDN / Cloudflare  (TLS, DDoS, caching)                          │
└────────────────────────────┬─────────────────────────────────────┘
                             │
                    ┌────────┴────────┐
                    │  frontend       │  nginx serving static React build
                    │  (port 80)      │  + reverse-proxy for /api & /ws
                    └────────┬────────┘
                             │
                    ┌────────┴────────┐
                    │  backend        │  FastAPI + uvicorn, 2 workers
                    │  (port 8001)    │  WebSocket broadcast, Resend, Twilio
                    └──┬──────┬───────┘
                       │      │
            ┌──────────┘      └──────────┐
            ▼                            ▼
       ┌─────────┐                ┌──────────────┐
       │ MongoDB │                │ S3-compat    │  images, documents
       │ (Atlas  │                │ (AWS / R2 /  │
       │  or DO) │                │  Spaces)     │
       └─────────┘                └──────────────┘
```

All services are packaged as Docker images. The storage backend is
**pluggable** (`STORAGE_BACKEND=inline` for base64-in-DB, or `s3` for external
object storage).

---

## 2. One-minute local preview

```bash
cp .env.example .env          # edit admin password + secrets
docker compose --profile prod up -d --build
docker compose logs -f backend frontend
```

Open <http://localhost>. Admin login is `ADMIN_EMAIL` / `ADMIN_PASSWORD` from
the `.env` file.

> On first boot, the backend seeds a default admin user and a 5-car demo
> catalog. Delete everything with:
> `docker compose exec mongo mongosh -u "$MONGO_ROOT_USER" -p "$MONGO_ROOT_PASSWORD" --authenticationDatabase admin --eval "use $DB_NAME; db.dropDatabase()"`

---

## 3. Single-VPS deployment

Works on any box with Docker installed (Hetzner CX22, DO Droplet, Vultr…).

### 3.1  Provision

```bash
ssh root@your-server
apt-get update && apt-get install -y ca-certificates curl
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
  https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update && apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
```

### 3.2  Fetch + configure

```bash
git clone https://github.com/<your-org>/autoandbid.git /opt/autoandbid
cd /opt/autoandbid
cp .env.example .env
nano .env                     # set APP_URL, MONGO_*, S3_*, ADMIN_*
```

### 3.3  First boot

```bash
docker compose --profile prod up -d --build
docker compose ps
curl -f http://127.0.0.1/healthz && echo "frontend ok"
curl -f http://127.0.0.1/api/healthz && echo "backend ok"
```

### 3.4  TLS with Caddy (zero-config)

In front of the compose stack:

```bash
# /etc/caddy/Caddyfile
auto-bid.bg, auto-bid.ro, auto-bid.com {
    reverse_proxy 127.0.0.1:80
}
```

```bash
apt-get install -y caddy
systemctl enable --now caddy
```

Caddy will obtain/renew Let's Encrypt certificates automatically.

### 3.5  Updates

```bash
cd /opt/autoandbid
git pull
docker compose --profile prod up -d --build
```

Rollback: `docker compose down && git checkout <tag> && docker compose up -d --build`.

---

## 4. Managed hosting options

### Railway

1. **Fork the repo on GitHub.**
2. Create a new Railway project → **Deploy from GitHub repo** → select the fork.
3. Railway detects the monorepo. Create **two services**:
   * `backend` — Root dir `backend/`, Dockerfile detected automatically.
   * `frontend` — Root dir `frontend/`, add build arg
     `REACT_APP_BACKEND_URL=$${{backend.RAILWAY_PUBLIC_DOMAIN}}` and
     runtime var `BACKEND_HOST=$${{backend.RAILWAY_PRIVATE_DOMAIN}}:8001`.
4. Add a **MongoDB plugin** (or connect Atlas):
   * Set `MONGO_URL` on backend service to the connection string.
   * Leave `MONGO_ROOT_USER/PASSWORD` unset — backend uses `MONGO_URL` directly.
5. Fill in all remaining secrets from `.env.example` under the backend service → Variables.
6. Attach custom domains (`auto-bid.bg/.ro/.com`) to the frontend service.

Railway charges per-minute. Expect ~\$8-15/mo for light traffic.

### Render

Render supports a top-level `render.yaml` blueprint. Add:

```yaml
services:
  - type: web
    name: backend
    runtime: docker
    dockerfilePath: ./backend/Dockerfile
    dockerContext: ./backend
    healthCheckPath: /api/healthz
    envVars:
      - fromGroup: autoandbid-secrets
  - type: web
    name: frontend
    runtime: docker
    dockerfilePath: ./frontend/Dockerfile
    dockerContext: ./frontend
    envVars:
      - key: BACKEND_HOST
        value: backend:8001
databases:
  - name: mongo
    plan: starter
    databaseName: autoandbid
```

Then in the Render dashboard create an **Environment Group** (`autoandbid-secrets`)
with the entries from `.env.example` and attach it to the backend.

### DigitalOcean App Platform

Use `doctl apps create --spec do-app-spec.yaml`:

```yaml
name: autoandbid
services:
  - name: backend
    dockerfile_path: backend/Dockerfile
    source_dir: backend
    instance_size_slug: professional-xs
    http_port: 8001
    health_check:
      http_path: /api/healthz
    envs:
      - { key: MONGO_URL, type: SECRET, value: ${mongo.DATABASE_URL} }
      # …repeat for every var in .env.example
  - name: frontend
    dockerfile_path: frontend/Dockerfile
    source_dir: frontend
    instance_size_slug: basic-xxs
    http_port: 80
    envs:
      - { key: BACKEND_HOST, value: "backend:8001" }
databases:
  - name: mongo
    engine: MONGODB
    production: true
```

Attach DigitalOcean Spaces for object storage — set the S3_\* variables on the
backend service to the Spaces credentials.

### Fly.io

Fly requires splitting into two apps (one per Dockerfile). A sample
`fly.toml` for the backend is below; clone it for the frontend.

```toml
# fly.backend.toml
app = "autoandbid-backend"
primary_region = "fra"
[build]
  dockerfile = "backend/Dockerfile"
[http_service]
  internal_port = 8001
  force_https = true
  auto_stop_machines = false
  auto_start_machines = true
  min_machines_running = 1
[[http_service.checks]]
  interval = "30s"
  method = "GET"
  path = "/api/healthz"
```

Use Fly Mongo Postgres equivalent or, better, connect to Atlas.

---

## 5. Object storage for uploads

By default the app keeps images as base64 data URLs in MongoDB
(`STORAGE_BACKEND=inline`). This works fine up to ~50k images but bloats DB
size and egress cost.

Switch to S3-compatible storage:

1. Create a bucket on **AWS S3 / Cloudflare R2 / DigitalOcean Spaces / Backblaze B2**.
2. Make the bucket publicly readable (the app uploads with `ACL=public-read`).
3. Put a CDN in front if you care about global delivery (Cloudflare works out of the box with R2).
4. Fill in the `S3_*` variables from `.env.example` and set `STORAGE_BACKEND=s3`.
5. Redeploy. Newly-created auctions will have URLs in `images[]`; older
   documents keep their inline base64 values and continue to work.

MinIO is bundled in `docker-compose.yml` for single-VPS deployments — it
exposes an S3-compatible API on port 9000 and persists to a Docker volume.

### One-time migration of old base64 images

```bash
docker compose exec backend python - <<'PY'
import asyncio, os
from motor.motor_asyncio import AsyncIOMotorClient
from storage import store_image

async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    cursor = db.auctions.find({"images.0": {"$regex": "^data:"}}, {"_id": 0, "id": 1, "images": 1})
    async for doc in cursor:
        new_images = [store_image(u) for u in doc["images"]]
        await db.auctions.update_one({"id": doc["id"]}, {"$set": {"images": new_images}})
        print("migrated", doc["id"])

asyncio.run(main())
PY
```

---

## 6. Environment reference

See [`.env.example`](./.env.example) for the authoritative list.

| Variable | Required | Purpose |
|----------|:--------:|---------|
| `MONGO_URL` | ✓ | Mongo connection string (built from `MONGO_ROOT_*` in compose) |
| `DB_NAME` | ✓ | Mongo database name |
| `JWT_SECRET` | ✓ | Signs auth tokens — rotate to force logout for all users |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | ✓ | Seeded on first boot if no admin exists |
| `APP_URL` | ✓ | Public HTTPS origin (used in emails, OG tags, JSON-LD) |
| `REACT_APP_BACKEND_URL` | ✓ | Where the SPA sends API requests — usually same as APP_URL |
| `CORS_ORIGINS` | ✓ | Comma-separated list of allowed origins |
| `STORAGE_BACKEND` | — | `inline` (default) or `s3` |
| `S3_*` | if S3 | Bucket, keys, endpoint, public base URL |
| `RESEND_API_KEY` | — | Transactional email — disable if blank |
| `TWILIO_*` | — | SMS + phone 2FA — disable if blank |
| `EMERGENT_LLM_KEY` | — | Auto-translate descriptions + comments — disable if blank |

---

## 7. Secrets rotation & backups

**Rotating `JWT_SECRET`** invalidates all sessions. Do it if you suspect a
token leak. Users will need to log in again.

**MongoDB backup** (daily cron on the VPS):

```bash
docker exec $(docker compose ps -q mongo) mongodump \
    --uri "mongodb://$MONGO_ROOT_USER:$MONGO_ROOT_PASSWORD@127.0.0.1:27017/?authSource=admin" \
    --archive --gzip > /var/backups/autoandbid-$(date +%F).archive.gz
```

Ship to S3 / Backblaze for off-site redundancy.

**Restore**:

```bash
docker exec -i $(docker compose ps -q mongo) mongorestore \
    --uri "mongodb://$MONGO_ROOT_USER:$MONGO_ROOT_PASSWORD@127.0.0.1:27017/?authSource=admin" \
    --archive --gzip --drop < autoandbid-2026-02-20.archive.gz
```

---

## 8. Observability & logs

- Container logs: `docker compose logs -f backend frontend`
- Structured JSON logs: the backend emits one JSON line per request to stdout.
  Ship to Loki/Grafana Cloud/Datadog via standard Docker log drivers.
- Health endpoints: `GET /api/healthz` (liveness), `GET /api/readyz` (readiness — pings Mongo).
- WebSocket stats: `GET /api/admin/ws/stats` (admin token required).

---

## 9. Scaling playbook

| Bottleneck | Fix |
|------------|-----|
| Backend CPU | Bump `WEB_CONCURRENCY=4` and CPU units on the PaaS. |
| DB writes | Switch to MongoDB Atlas M10+ with provisioned IOPS. |
| Image egress | Enable S3 + Cloudflare CDN. |
| WebSocket broadcast lag | Run 2+ backend replicas + Redis pub/sub (P2 roadmap). |
| Front-end TTFB | Let Cloudflare cache the SPA shell with `s-maxage=60, must-revalidate`. |

---

## 10. Future: PostgreSQL migration

The current data layer uses MongoDB via `motor`. A Postgres migration is on
the P2 roadmap and would involve:

1. Defining SQLAlchemy 2.0 models mirroring the 12 collections.
2. Rewriting each of the ~200 CRUD calls in `server.py`.
3. Converting aggregation pipelines to SQL (GROUP BY + JSON functions).
4. Adding Alembic for schema migrations.
5. End-to-end regression across auth, bidding, admin, stats, WebSocket flows.

Tracked in [`memory/ROADMAP.md`](./memory/ROADMAP.md).  Until then, managed
Mongo (Atlas, DO, Render) is the supported production database. The
deployment surface, Docker images and storage layer remain unchanged once
that migration lands.
