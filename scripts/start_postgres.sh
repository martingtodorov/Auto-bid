#!/bin/bash
# PostgreSQL startup wrapper for Auto&Bid bidding subsystem.
#
# Why this script exists:
#   The container's overlay filesystem (everything outside /app) is wiped on
#   container restarts. That means /usr/lib/postgresql, /var/lib/postgresql,
#   and the `postgres` OS user all disappear. /app is the only persistent
#   volume.
#
#   This script makes PG durable across restarts by:
#     1. (Re)creating the `postgres` OS user when /etc/passwd is reset.
#     2. Reinstalling postgresql-15 packages from a /app/data/pkgs cache
#        (~5-10s offline) or from network (~60-90s) on first boot.
#     3. Storing the data directory in /app/data/pgdata (persistent).
#     4. Bootstrapping the autobid user + autobid_bids database on first run.
#     5. exec'ing postgres in the foreground so supervisor can manage it.
#
# Note: we use /app/data/pgdata as BOTH config_file location and data_dir,
# so we don't depend on /etc/postgresql/15/main being present (the package
# post-install can't always recreate the cluster config in a container).

set -uo pipefail

PG_VERSION=15
PG_BIN="/usr/lib/postgresql/${PG_VERSION}/bin"
PG_DATA="/app/data/pgdata"
PG_PKG_CACHE="/app/data/pkgs"
PG_LOG="/var/log/supervisor/postgresql-bootstrap.log"

log() {
  echo "[$(date '+%F %T')] $*" | tee -a "${PG_LOG}"
}

mkdir -p /var/log/supervisor /app/data "${PG_PKG_CACHE}"
touch "${PG_LOG}" || true

# 1) (Re)create postgres OS user/group if they're missing.
if ! id postgres > /dev/null 2>&1; then
  log "Creating postgres OS user/group..."
  groupadd --system --gid 105 postgres 2>> "${PG_LOG}" \
    || groupadd --system postgres 2>> "${PG_LOG}" \
    || true
  useradd --system --gid postgres --no-create-home \
          --home /var/lib/postgresql --shell /bin/bash \
          --uid 105 postgres 2>> "${PG_LOG}" \
    || useradd --system --gid postgres --no-create-home \
               --home /var/lib/postgresql --shell /bin/bash postgres 2>> "${PG_LOG}" \
    || true
fi

# 2) Reinstall PG binaries when /usr was wiped.
if [ ! -x "${PG_BIN}/postgres" ]; then
  log "PostgreSQL binaries missing — reinstalling postgresql-${PG_VERSION}..."
  export DEBIAN_FRONTEND=noninteractive

  # Repair any half-installed dpkg state from a previous interrupted boot.
  dpkg --configure -a >> "${PG_LOG}" 2>&1 || true

  # Fast path: cached .deb files (~5-10s offline).
  if compgen -G "${PG_PKG_CACHE}"/*.deb > /dev/null; then
    log "Found cached .deb files in ${PG_PKG_CACHE} — force-reinstalling offline"
    dpkg --force-confnew --force-overwrite -i "${PG_PKG_CACHE}"/*.deb >> "${PG_LOG}" 2>&1 || true
    apt-get install -fy --no-install-recommends >> "${PG_LOG}" 2>&1 || true
  fi

  # Fallback: network apt.
  if [ ! -x "${PG_BIN}/postgres" ]; then
    log "Cached install incomplete — downloading via network apt..."
    apt-get update -qq >> "${PG_LOG}" 2>&1 || true
    apt-get install -y --reinstall --no-install-recommends \
        postgresql-${PG_VERSION} postgresql-contrib >> "${PG_LOG}" 2>&1 || true
    # Refresh the cache for next boot.
    rm -f "${PG_PKG_CACHE}"/*.deb 2>/dev/null || true
    cd "${PG_PKG_CACHE}" && \
      apt-get download postgresql-${PG_VERSION} postgresql-client-${PG_VERSION} \
                       postgresql-common postgresql-client-common libpq5 \
                       libcommon-sense-perl libjson-perl libjson-xs-perl \
                       libtypes-serialiser-perl ssl-cert >> "${PG_LOG}" 2>&1 || true
    cd /
  fi

  if [ ! -x "${PG_BIN}/postgres" ]; then
    log "FATAL: Unable to install PostgreSQL binaries"
    exit 1
  fi
  log "PostgreSQL install complete."
fi

# 3) Initialise the persistent data dir on first run. We embed the config
#    inside ${PG_DATA} itself so we never depend on /etc/postgresql.
if [ ! -s "${PG_DATA}/PG_VERSION" ]; then
  log "Initialising new persistent data directory at ${PG_DATA}..."
  mkdir -p "${PG_DATA}"
  chown -R postgres:postgres "${PG_DATA}"
  chmod 700 "${PG_DATA}"
  sudo -u postgres "${PG_BIN}/initdb" -D "${PG_DATA}" --auth-local=trust --auth-host=md5 >> "${PG_LOG}" 2>&1
  log "initdb finished."

  # Make sure the runtime dir for the unix socket exists.
  mkdir -p /var/run/postgresql
  chown postgres:postgres /var/run/postgresql

  # Bootstrap the autobid user + db on a temporary local-only PG.
  log "Starting temporary PG to create autobid role/db..."
  sudo -u postgres "${PG_BIN}/pg_ctl" -D "${PG_DATA}" -l "${PG_LOG}" -w start >> "${PG_LOG}" 2>&1
  sudo -u postgres "${PG_BIN}/psql" -v ON_ERROR_STOP=1 <<-SQL >> "${PG_LOG}" 2>&1 || true
CREATE USER autobid WITH PASSWORD 'autobid_pass';
CREATE DATABASE autobid_bids OWNER autobid;
GRANT ALL PRIVILEGES ON DATABASE autobid_bids TO autobid;
SQL
  sudo -u postgres "${PG_BIN}/psql" -d autobid_bids -c "GRANT ALL ON SCHEMA public TO autobid;" >> "${PG_LOG}" 2>&1 || true
  sudo -u postgres "${PG_BIN}/pg_ctl" -D "${PG_DATA}" -m fast stop -w >> "${PG_LOG}" 2>&1
  log "Bootstrap done."
fi

# 4) Repair ownership in case the volume came from a system with a different
#    postgres UID. Skip if already correct (fast path).
if [ "$(stat -c %U "${PG_DATA}" 2>/dev/null)" != "postgres" ]; then
  log "Fixing ownership on ${PG_DATA}..."
  chown -R postgres:postgres "${PG_DATA}"
fi
chmod 700 "${PG_DATA}"

# 5) Ensure the data dir has its own postgresql.conf + pg_hba.conf.
#    Older pgdata snapshots may have had these in /etc/postgresql/...
#    instead — when /etc gets wiped on container restart, the cluster
#    cannot start without an embedded config. We seed minimal ones here.
if [ ! -f "${PG_DATA}/postgresql.conf" ]; then
  log "Seeding default postgresql.conf into ${PG_DATA}..."
  if [ -f "/usr/share/postgresql/${PG_VERSION}/postgresql.conf.sample" ]; then
    cp "/usr/share/postgresql/${PG_VERSION}/postgresql.conf.sample" "${PG_DATA}/postgresql.conf"
  else
    cat > "${PG_DATA}/postgresql.conf" <<'EOF'
listen_addresses = 'localhost'
port = 5432
max_connections = 100
unix_socket_directories = '/var/run/postgresql'
shared_buffers = 128MB
dynamic_shared_memory_type = posix
log_destination = 'stderr'
logging_collector = off
log_timezone = 'UTC'
datestyle = 'iso, mdy'
timezone = 'UTC'
default_text_search_config = 'pg_catalog.english'
EOF
  fi
  # Make sure these settings are present even when using sample defaults.
  cat >> "${PG_DATA}/postgresql.conf" <<'EOF'

# Auto&Bid container overrides
listen_addresses = 'localhost'
port = 5432
unix_socket_directories = '/var/run/postgresql'
fsync = on
synchronous_commit = on
full_page_writes = on
EOF
  chown postgres:postgres "${PG_DATA}/postgresql.conf"
fi

if [ ! -f "${PG_DATA}/pg_hba.conf" ]; then
  log "Seeding default pg_hba.conf into ${PG_DATA}..."
  cat > "${PG_DATA}/pg_hba.conf" <<'EOF'
# Auto&Bid container default — local trust + 127.0.0.1 md5
local   all             postgres                                trust
local   all             all                                     trust
host    all             all             127.0.0.1/32            md5
host    all             all             ::1/128                 md5
EOF
  chown postgres:postgres "${PG_DATA}/pg_hba.conf"
  chmod 600 "${PG_DATA}/pg_hba.conf"
fi

if [ ! -f "${PG_DATA}/pg_ident.conf" ]; then
  touch "${PG_DATA}/pg_ident.conf"
  chown postgres:postgres "${PG_DATA}/pg_ident.conf"
  chmod 600 "${PG_DATA}/pg_ident.conf"
fi

# 6) Ensure runtime socket dir exists (overlay FS resets /var/run on cold boot).
mkdir -p /var/run/postgresql
chown postgres:postgres /var/run/postgresql

# 7) Exec PG in foreground so supervisor monitors it directly. Config lives
#    inside the data dir, so we don't depend on /etc/postgresql.
log "Starting PostgreSQL on persistent data dir ${PG_DATA}..."
exec sudo -u postgres "${PG_BIN}/postgres" -D "${PG_DATA}"
