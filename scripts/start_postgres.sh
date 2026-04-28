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
#     1. Installing the postgresql-15 packages if the binaries are missing
#        (also (re)creates the `postgres` OS user via package post-install).
#     2. Storing the data directory in /app/data/pgdata (persistent).
#     3. Bootstrapping the autobid user + autobid_bids database on first run.
#     4. exec'ing postgres in the foreground so supervisor can manage it.

set -euo pipefail

PG_VERSION=15
PG_BIN="/usr/lib/postgresql/${PG_VERSION}/bin"
PG_DATA="/app/data/pgdata"
PG_CONF_SRC="/etc/postgresql/${PG_VERSION}/main/postgresql.conf"
PG_LOG="/var/log/supervisor/postgresql-bootstrap.log"

log() { echo "[$(date '+%F %T')] $*" | tee -a "${PG_LOG}"; }

mkdir -p /var/log/supervisor /app/data
touch "${PG_LOG}" || true

# 1) Install postgres binaries + create `postgres` OS user if missing.
if [ ! -x "${PG_BIN}/postgres" ] || ! id postgres > /dev/null 2>&1; then
  log "PostgreSQL binaries missing — installing postgresql-${PG_VERSION}..."
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq >> "${PG_LOG}" 2>&1 || true
  apt-get install -y --no-install-recommends \
      postgresql-${PG_VERSION} postgresql-contrib >> "${PG_LOG}" 2>&1
  log "PostgreSQL install complete."
fi

# 2) Initialise the persistent data dir on first run.
if [ ! -s "${PG_DATA}/PG_VERSION" ]; then
  log "Initialising new persistent data directory at ${PG_DATA}..."
  mkdir -p "${PG_DATA}"
  chown -R postgres:postgres "${PG_DATA}"
  chmod 700 "${PG_DATA}"
  sudo -u postgres "${PG_BIN}/initdb" -D "${PG_DATA}" --auth-local=trust --auth-host=md5 >> "${PG_LOG}" 2>&1
  log "initdb finished."

  # Start temporarily on a unix socket to seed user + db.
  log "Starting temporary PG to create autobid role/db..."
  sudo -u postgres "${PG_BIN}/pg_ctl" -D "${PG_DATA}" -l "${PG_LOG}" -w start
  sudo -u postgres "${PG_BIN}/psql" -v ON_ERROR_STOP=1 <<-SQL >> "${PG_LOG}" 2>&1
    CREATE USER autobid WITH PASSWORD 'autobid_pass';
    CREATE DATABASE autobid_bids OWNER autobid;
    GRANT ALL PRIVILEGES ON DATABASE autobid_bids TO autobid;
SQL
  sudo -u postgres "${PG_BIN}/psql" -d autobid_bids -c "GRANT ALL ON SCHEMA public TO autobid;" >> "${PG_LOG}" 2>&1
  sudo -u postgres "${PG_BIN}/pg_ctl" -D "${PG_DATA}" -m fast stop -w
  log "Bootstrap done."
fi

# 3) Ensure proper ownership (in case the volume was restored from elsewhere).
chown -R postgres:postgres "${PG_DATA}"

# 4) Exec PG in foreground so supervisor monitors it directly.
log "Starting PostgreSQL on persistent data dir ${PG_DATA}..."
exec sudo -u postgres "${PG_BIN}/postgres" -D "${PG_DATA}" \
     -c config_file="${PG_CONF_SRC}" \
     -c data_directory="${PG_DATA}"
