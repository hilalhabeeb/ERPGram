#!/usr/bin/env bash
# Production entrypoint: prepare the app, then hand off to gunicorn.
#
# Unlike the dev entrypoint, there is no bind-mount hiding the image's baked
# assets, so the CSS bundle and vendored JS/fonts are already in place. What
# production adds is collectstatic (the CompressedManifestStaticFilesStorage
# backend refuses to serve without a manifest) and a real WSGI server.
set -euo pipefail

echo "Waiting for Postgres..."
until uv run python -c "import os, psycopg; psycopg.connect(os.environ['DATABASE_URL']).close()" >/dev/null 2>&1; do
    sleep 1
done
echo "Postgres is up."

# Translations → .mo (gitignored, so compile on every boot; it is cheap).
uv run python manage.py compilemessages -l ar -l en >/dev/null 2>&1 || true

# Gather hashed static files for WhiteNoise to serve.
echo "Collecting static files..."
uv run python manage.py collectstatic --noinput

# Apply migrations. Single web replica, so no coordination needed; if you ever
# run more than one, move this to a one-off job instead of the boot path.
echo "Applying migrations..."
uv run python manage.py migrate --noinput

exec "$@"
