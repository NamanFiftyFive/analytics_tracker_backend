#!/usr/bin/env bash
# Copies all DATA from the local Homebrew Postgres (localhost:5432) into the Docker database
# (the "db" service). Run from backend/ after `docker compose up -d`:
#
#     scripts/copy_local_db_to_docker.sh
#
# Only data is copied: the Docker database already has the tables, created by the migrate
# service from the same migrations. schema_migrations is skipped for that reason.
# Refuses to run if the Docker database already has users, so nothing is overwritten.
set -euo pipefail

cd "$(dirname "$0")/.."   # backend/, where docker-compose.yml and .env are
# Read just the two values needed (not `source .env`: it isn't shell syntax, e.g. APP_NAME has a space).
POSTGRES_USER=$(grep '^POSTGRES_USER=' .env | cut -d= -f2-)
POSTGRES_DB=$(grep '^POSTGRES_DB=' .env | cut -d= -f2-)

existing=$(docker compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "SELECT count(*) FROM users")
if [ "$existing" != "0" ]; then
    echo "The Docker database already has $existing users; not copying (would duplicate data)."
    echo "To start over: docker compose down && docker volume rm analytics_pgdata14 && docker compose up -d"
    exit 1
fi

# --disable-triggers: load tables in any order without foreign-key checks failing midway
#   (needs a superuser, which POSTGRES_USER is inside the container).
# --single-transaction + ON_ERROR_STOP: all or nothing.
pg_dump -h localhost -p 5432 -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
        --data-only --disable-triggers --no-owner --no-privileges \
        --exclude-table=schema_migrations \
    | docker compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
        --quiet --single-transaction -v ON_ERROR_STOP=1 > /dev/null

echo "Copied. Row counts (local vs Docker):"
for table in organizations users organization_members projects api_keys persons sessions events event_definitions; do
    local_count=$(psql -h localhost -p 5432 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "SELECT count(*) FROM $table")
    docker_count=$(docker compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "SELECT count(*) FROM $table")
    printf "  %-22s %8s %8s\n" "$table" "$local_count" "$docker_count"
done
