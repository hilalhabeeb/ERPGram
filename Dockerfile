# Django app image. Python 3.12 + uv, with the Tailwind standalone CLI baked in
# so no Node.js is ever required.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    DJANGO_SETTINGS_MODULE=config.settings.local

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates gettext \
    && rm -rf /var/lib/apt/lists/*

# Tailwind standalone binary (pinned).
ARG TAILWIND_VERSION=v3.4.17
RUN curl -fsSL -o /usr/local/bin/tailwindcss \
    "https://github.com/tailwindlabs/tailwindcss/releases/download/${TAILWIND_VERSION}/tailwindcss-linux-x64" \
    && chmod +x /usr/local/bin/tailwindcss

# Vendor front-end assets (HTMX, Alpine, fonts) into a cache outside /app so
# they survive the dev bind-mount; the entrypoint seeds them into static/ if
# missing. No CDN is referenced at runtime — the app serves these locally.
RUN mkdir -p /opt/vendor/js /opt/vendor/fonts \
    && curl -fsSL -o /opt/vendor/js/htmx.min.js https://unpkg.com/htmx.org@2.0.3/dist/htmx.min.js \
    && curl -fsSL -o /opt/vendor/js/alpine.min.js https://unpkg.com/alpinejs@3.14.1/dist/cdn.min.js \
    && curl -fsSL -o /opt/vendor/fonts/inter-400.woff2 https://cdn.jsdelivr.net/npm/@fontsource/inter@5.0.18/files/inter-latin-400-normal.woff2 \
    && curl -fsSL -o /opt/vendor/fonts/inter-500.woff2 https://cdn.jsdelivr.net/npm/@fontsource/inter@5.0.18/files/inter-latin-500-normal.woff2 \
    && curl -fsSL -o /opt/vendor/fonts/inter-600.woff2 https://cdn.jsdelivr.net/npm/@fontsource/inter@5.0.18/files/inter-latin-600-normal.woff2 \
    && curl -fsSL -o /opt/vendor/fonts/plex-arabic-400.woff2 https://cdn.jsdelivr.net/npm/@fontsource/ibm-plex-sans-arabic@5.0.20/files/ibm-plex-sans-arabic-arabic-400-normal.woff2 \
    && curl -fsSL -o /opt/vendor/fonts/plex-arabic-500.woff2 https://cdn.jsdelivr.net/npm/@fontsource/ibm-plex-sans-arabic@5.0.20/files/ibm-plex-sans-arabic-arabic-500-normal.woff2

# Install dependencies first for better layer caching.
COPY pyproject.toml ./
RUN uv sync --group dev

# Application source.
COPY . .

# Build the CSS bundle (templates are present, so content scanning works).
RUN tailwindcss -i static/src/input.css -o static/css/app.css --minify

RUN chmod +x docker/entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["uv", "run", "python", "manage.py", "runserver", "0.0.0.0:8000"]
