#!/bin/sh
# Restore the database from object storage (if a replica exists), then run the
# API under Litestream so every write is streamed back to the bucket.
set -e
if [ -n "$LITESTREAM_BUCKET" ]; then
  litestream restore -if-db-not-exists -if-replica-exists /data/khidki.db
  litestream restore -if-db-not-exists -if-replica-exists /data/sessions.db
  exec litestream replicate -exec "uvicorn khidki.api:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers"
fi
exec uvicorn khidki.api:app --host 0.0.0.0 --port "${PORT:-8080}" --proxy-headers
