# ERPGRAM

[![CI](https://github.com/hilalhabeeb/ERPGram/actions/workflows/ci.yml/badge.svg)](https://github.com/hilalhabeeb/ERPGram/actions/workflows/ci.yml)

A multi-tenant ERP platform with a shared core — tenancy with two-layer
isolation, email/password auth, roles and permissions, and an RTL-ready,
internationalised app shell — plus **industry modules** selected per tenant.

The first module is **manpower**: GCC agencies supplying housemaids, drivers,
cooks and carers to household sponsors, including placements that double as the
agency's invoice.

> **Working on this?** [CLAUDE.md](CLAUDE.md) has the commands, the architecture
> and the rules that have already caused bugs. [BACKLOG.md](BACKLOG.md) has what
> is planned next.

> Everything runs in Docker: a `db` service (Postgres 16) and a `web` service
> (Django 5.1 + the Tailwind standalone CLI — no Node.js). This is a deliberate
> deviation from "run Django on the host"; it makes a clone reproducible and lets
> the test suite run the same way everywhere.

---

## Quick start (fresh clone → working login in ~5 minutes)

Prerequisites: **Docker Desktop** (Compose v2) and **git**. Nothing else —
no Python, Node, or Postgres on the host.

### macOS / Linux

```bash
cp .env.example .env          # optional: only needed for host (non-Docker) runs
make install                  # build the image (installs deps, Tailwind, fonts, HTMX/Alpine)
make migrate                  # create the schema + enable row-level security
make seed                     # two demo tenants with owners and members
make dev                      # http://localhost:8010
```

### Windows (PowerShell)

```powershell
Copy-Item .env.example .env
./tasks.ps1 install
./tasks.ps1 migrate
./tasks.ps1 seed
./tasks.ps1 dev               # http://localhost:8010
```

Open <http://localhost:8010> and sign in with a seeded account.

> **Port note.** The app is published on **8010** because editors such as Cursor
> and VS Code often hold port 8000. To use a different host port, set `WEB_PORT`
> in `.env` (e.g. `WEB_PORT=8020`) and re-run `docker compose up -d`.

| Tenant        | Role   | Email               | Password        |
| ------------- | ------ | ------------------- | --------------- |
| Acme Trading  | owner  | `owner@acme.test`   | `demo-pass-123` |
| Acme Trading  | member | `sara@acme.test`    | `demo-pass-123` |
| Globex LLC    | owner  | `owner@globex.test` | `demo-pass-123` |
| Globex LLC    | member | `lina@globex.test`  | `demo-pass-123` |

Emails (invitations, password resets) print to the `web` container logs in dev
(console email backend).

---

## Common tasks

| Task                     | macOS / Linux        | Windows                       |
| ------------------------ | -------------------- | ----------------------------- |
| Build images             | `make install`       | `./tasks.ps1 install`         |
| Start Postgres           | `make up`            | `./tasks.ps1 up`              |
| Migrate                  | `make migrate`       | `./tasks.ps1 migrate`         |
| Seed demo data           | `make seed`          | `./tasks.ps1 seed`            |
| Run app + Tailwind watch | `make dev`           | `./tasks.ps1 dev`             |
| Tests                    | `make test`          | `./tasks.ps1 test`            |
| Lint / format            | `make lint` / `fmt`  | `./tasks.ps1 lint` / `fmt`    |
| Full CI gate locally     | `make ci`            | `./tasks.ps1 ci`              |
| Extract translations     | `make messages`      | `./tasks.ps1 messages`        |
| Compile translations     | `make compilemessages` | `./tasks.ps1 compilemessages` |

## Industries (domains)

A tenant picks its **industry** when it signs up at `/signup/`, and that decides
which modules exist for it. This is a different axis from permissions:

| | question it answers |
| --- | --- |
| **domain** | does this feature exist for this customer? |
| **permission** | may *this user* use a feature their tenant has? |

Nav entries, permissions and apps each declare the domains they belong to (see
[`apps/core/domains.py`](apps/core/domains.py)), so adding an industry means
adding a `Domain` plus an app that tags its own entries — not editing the shell.
A tenant outside a supported industry still gets the shared core (organisation
structure, users, roles).

Requesting a module your tenant does not have returns **404, not 403**: the
feature does not exist for you, so confirming the URL is real would mislead.

### Manpower — GCC domestic-worker supply

The first industry module. It models agencies that supply housemaids, drivers,
cooks and carers to household **sponsors**, where the worker ends up on the
sponsor's visa. Two fields drive most screens:

- `Worker.availability` — can this worker be offered right now?
- `Worker.location` — already **in country** (a quick visa transfer) or still
  **overseas** (travel, medical and visa processing first)

Masters: worker, sponsor, occupation, skill, agent (overseas partner),
accommodation, document type and worker document. Country and language are
shared reference data rather than tenant-scoped — they are objective facts, so
there is one row per country rather than one per agency.

```bash
make seed-manpower     # or: ./tasks.ps1 seed-manpower
```

seeds a demo agency (Gulf Domestic Services) with 28 workers across Indonesia,
the Philippines, Sri Lanka, Ethiopia, Kenya, India and Nepal, plus agents,
accommodation and sponsors. Sign in as `owner@gulfdomestic.test`.

## Deployment

Production runs on a single VPS with Docker — Postgres + gunicorn + Caddy
(automatic HTTPS) — and is fully separate from local dev. See
[DEPLOY.md](DEPLOY.md) for the runbook: DNS, secrets, `docker-compose.prod.yml`,
backups and updates.

---

## Continuous integration

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs on every push to
`main` and on every pull request: ruff lint, ruff format check, a
missing-migrations guard, Django system checks, and the full test suite against
Postgres 16.

`make ci` / `./tasks.ps1 ci` runs the identical set of checks locally, so you
can catch a red build before pushing.

CI deliberately creates the same non-superuser `erpgram_app` role used in
development and asserts it cannot bypass row-level security. Running the tests
as the Postgres superuser would ignore the RLS policies and the tenant-isolation
tests would pass without proving anything.

The Django admin ("back office") is at **`/backoffice/`** (configurable via
`DJANGO_ADMIN_URL`), staff-only. It is the internal tool for seeding tenants and
users — it is not the product. Create a staff user with
`make shell`/`createsuperuser` if you need it.

---

## Architecture

```
config/            settings (base/local/production), urls, wsgi, asgi
apps/
  core/            abstract models, tenant contextvars, RLS helper, middleware
  tenancy/         Tenant, Company, Branch, Department  (+ seed command)
  accounts/        custom User, Membership, auth views/services
  ui/              app shell, template components, dashboard + settings pages
templates/         base, shell, auth, registration, error pages
static/            Tailwind source + build, vendored HTMX/Alpine, self-hosted fonts
tests/             tenant isolation, auth, tenant switching, permissions
```

### Multi-tenancy — two layers

1. **Application.** `TenantMiddleware` resolves the active tenant from
   `session["tenant_id"]` (falling back to the user's default `Membership`),
   stores it in a `contextvars` store, and attaches `request.tenant`. Every
   business model inherits `TenantScopedModel`, whose default manager filters on
   that store. An `all_tenants` manager is the escape hatch for admin/jobs.

2. **Database (row-level security).** The same middleware runs each request in a
   transaction and sets the `app.tenant_id` GUC. Every tenant-scoped table has an
   RLS policy:

   ```sql
   CREATE POLICY tenant_isolation ON <table>
     USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
     WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);
   ```

   Future modules enable this in one line:

   ```python
   from apps.core.db import enable_rls
   operations = [*enable_rls("myapp_widget")]
   ```

#### ⚠️ Database role — do not use a superuser

The application connects as **`erpgram_app`**, which is intentionally **not** a
superuser and does **not** have `BYPASSRLS`. A superuser (or a `BYPASSRLS` role)
**ignores every RLS policy**, silently defeating layer 2. The policies are also
`FORCE`d — because `erpgram_app` *owns* the tables (it runs migrations), and a
table owner is otherwise exempt from its own policies. `docker/postgres-init.sql`
creates the role with `NOSUPERUSER CREATEDB NOBYPASSRLS`.

Because RLS is forced, code that touches tenant-scoped tables **outside** a
request (seed, jobs, tests) must bind a tenant first:

```python
from apps.core.tenant import activate_tenant
with activate_tenant(tenant.id):
    Company.objects.create(...)
```

### Front end

Server-rendered Django templates, **HTMX** for partial updates and **Alpine.js**
for local UI state — no SPA. Design tokens live in `tailwind.config.js`; templates
use token classes (`bg-card`, `text-text-secondary`, `rounded-card`, …), never raw
hex. Reusable components are `{% include %}` partials in `apps/ui/templates/ui/`
(each documents its context variables at the top). Icons are vendored Lucide SVGs
exposed via `{% icon "users" css_class="w-5 h-5" %}`.

**RTL & i18n from day one.** Only logical properties (`ms/me/ps/pe/start/end`);
`dir` follows the active language; `en` and `ar` are enabled; every string is
wrapped in `{% trans %}`/`gettext_lazy`; the avatar menu has a language switcher.

---

## Testing

```bash
make test
```

Covers the critical paths: tenant isolation at **both** layers (ORM manager and
raw SQL against forced RLS), the login flow (success / bad password / lockout),
tenant switching (session + visible data), and owner-only access to the
organisation settings page.

---

## Running without Docker (optional)

You need Python 3.12, [uv](https://docs.astral.sh/uv/), and a Postgres 16 with the
`erpgram_app` role (see `docker/postgres-init.sql`). Then:

```bash
uv sync --group dev
uv run python manage.py migrate
uv run python manage.py seed
# build CSS with the Tailwind standalone CLI, then:
uv run python manage.py runserver
```
