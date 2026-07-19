#!/usr/bin/env bash
set -euo pipefail

echo "Waiting for Postgres..."
until uv run python -c "import os, psycopg; psycopg.connect(os.environ['DATABASE_URL']).close()" >/dev/null 2>&1; do
    sleep 1
done
echo "Postgres is up."

# The source tree is bind-mounted in dev, which hides assets baked into the
# image. Seed vendored JS/fonts from the build-time cache if missing.
mkdir -p static/vendor static/fonts static/css
[ -f static/vendor/htmx.min.js ] || cp /opt/vendor/js/htmx.min.js static/vendor/ 2>/dev/null || true
[ -f static/vendor/alpine.min.js ] || cp /opt/vendor/js/alpine.min.js static/vendor/ 2>/dev/null || true
for f in inter-400 inter-500 inter-600 plex-arabic-400 plex-arabic-500; do
    [ -f "static/fonts/$f.woff2" ] || cp "/opt/vendor/fonts/$f.woff2" static/fonts/ 2>/dev/null || true
done

# Build the CSS bundle if missing (bind-mount hides the image's copy).
if [ ! -f static/css/app.css ]; then
    echo "Building Tailwind CSS..."
    tailwindcss -i static/src/input.css -o static/css/app.css --minify || true
fi

# Compile translation catalogs if not already built.
if [ ! -f locale/ar/LC_MESSAGES/django.mo ]; then
    echo "Compiling translations..."
    uv run python manage.py compilemessages -l ar -l en >/dev/null 2>&1 || true
fi

uv run python manage.py migrate --noinput

exec "$@"
