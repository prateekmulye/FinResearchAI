#!/bin/sh
# WP-11 app entrypoint: migrate (when the warehouse is configured), then serve.
#
# DATABASE_URL set   -> run `alembic upgrade head`, retrying for ~30s while the
#                       db container finishes booting (depends_on healthy makes
#                       this belt-and-braces, not the primary wait).
# DATABASE_URL unset -> warehouse disabled; skip migrations entirely.
#
# If migrations still fail after the retries we exit non-zero rather than serve
# against an unmigrated schema; compose `restart: unless-stopped` retries us.
set -eu

if [ -n "${DATABASE_URL:-}" ]; then
    attempts=6
    i=1
    while :; do
        if alembic upgrade head; then
            echo "entrypoint: migrations up to date"
            break
        fi
        if [ "$i" -ge "$attempts" ]; then
            echo "entrypoint: alembic upgrade head failed after ${attempts} attempts" >&2
            exit 1
        fi
        echo "entrypoint: db not ready (attempt ${i}/${attempts}); retrying in 5s" >&2
        i=$((i + 1))
        sleep 5
    done
else
    echo "entrypoint: DATABASE_URL unset; skipping migrations"
fi

exec uvicorn src.api.main:app --host 0.0.0.0 --port "${PORT:-7860}" --workers 1
