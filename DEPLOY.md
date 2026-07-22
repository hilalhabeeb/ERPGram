# Deploying ERPGRAM

Production runs on a single Linux VPS with Docker: **Postgres + gunicorn +
Caddy**. Caddy terminates HTTPS (automatic Let's Encrypt certificates) and
serves user uploads; gunicorn runs Django; Postgres holds the data.

This is entirely separate from local development. `docker-compose.yml` (dev)
is untouched — you keep using `docker compose up` and `make seed` on your
machine exactly as before.

---

## What you need

- A VPS (e.g. Hetzner CX22, DigitalOcean, Linode) running Ubuntu 22.04+. 2 GB
  RAM is comfortable to start.
- A domain you control (you have this).
- SMTP credentials for outbound email (invites, password resets) — any provider
  (Mailgun, SES, Postmark, your host's SMTP).

---

## 1. Point DNS at the server

Create an **A record** for your domain (or subdomain, e.g. `erp.yourdomain.com`)
pointing at the server's public IP. Caddy cannot get a certificate until this
resolves, so do it first and give it a few minutes to propagate.

## 2. Prepare the server

```bash
ssh root@YOUR_SERVER_IP

# Install Docker Engine + compose plugin.
curl -fsSL https://get.docker.com | sh

# A firewall that allows SSH + web.
ufw allow OpenSSH && ufw allow 80 && ufw allow 443 && ufw --force enable
```

## 3. Get the code and configure

```bash
git clone https://github.com/hilalhabeeb/ERPGram.git
cd ERPGram

cp .env.prod.example .env.prod
nano .env.prod        # fill in every value — see the comments in the file
```

Generate the secrets:

```bash
# SECRET_KEY
python3 -c "import secrets; print(secrets.token_urlsafe(64))"
# POSTGRES_PASSWORD and APP_DB_PASSWORD (run twice; APP one: letters/digits only)
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
python3 -c "import secrets,string; print(''.join(secrets.choice(string.ascii_letters+string.digits) for _ in range(32)))"
```

Set `DOMAIN`, `ALLOWED_HOSTS`, and `CSRF_TRUSTED_ORIGINS` to your domain.

## 4. Launch

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build
```

First boot: the image builds, Postgres initialises the app role, migrations run,
static files are collected, and Caddy fetches the TLS certificate. Watch it:

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml logs -f
```

When Caddy logs `certificate obtained`, open `https://yourdomain.com`.

## 5. Create the first organisation

Two options:

- **Sign up through the app** — visit the site and use "Create your
  organisation". This is the real path a customer takes.
- **Load the demo data** (a throwaway showcase, not for a real tenant):

  ```bash
  docker compose --env-file .env.prod -f docker-compose.prod.yml \
    exec web uv run python manage.py seed_manpower
  ```

  The demo logins from `make seed-manpower` apply. Delete the demo tenant before
  going live for real.

---

## Operating it

**Deploy an update** (after `git push` from your machine):

```bash
cd ERPGram && git pull
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build
```

Migrations and collectstatic run automatically on boot.

**Back up the database** — the only irreplaceable state. Add a daily cron:

```bash
# /etc/cron.daily/erpgram-backup  (chmod +x)
cd /root/ERPGram && docker compose --env-file .env.prod -f docker-compose.prod.yml \
  exec -T db pg_dump -U erpgram_app erpgram | gzip > /root/backups/erpgram-$(date +\%F).sql.gz
```

Keep the backups off-box too (rsync/S3). Uploads live in the `media_prod`
volume — include it in your backup if sponsors upload documents/photos.

**Restore**:

```bash
gunzip -c backup.sql.gz | docker compose --env-file .env.prod \
  -f docker-compose.prod.yml exec -T db psql -U erpgram_app erpgram
```

---

## Notes & guarantees

- **Tenant isolation holds in production.** The app connects as `erpgram_app`,
  a non-superuser role without `BYPASSRLS`, so Postgres row-level security is
  enforced — the same guarantee CI asserts.
- **Secrets never enter the repo.** `.env.prod` is gitignored; the DB passwords
  are generated on the server; the image contains no secret.
- **One web replica** is assumed (migrations run on boot). To scale out, move
  `migrate` to a one-off release step and add replicas behind Caddy.
- The image currently includes dev tooling (pytest, ruff) for a single build
  path. Trimming to a slim prod image is a later optimisation, noted in
  [BACKLOG.md](BACKLOG.md).
