# ERPGRAM

A multi-tenant ERP platform. **Step 1** is the foundation: project scaffold,
tenancy model with two-layer isolation, email/password auth, and a polished,
RTL-ready, internationalised app shell with a reusable component library.
Business modules (CRM, inventory, HR, …) come in later steps.

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
| Extract translations     | `make messages`      | `./tasks.ps1 messages`        |
| Compile translations     | `make compilemessages` | `./tasks.ps1 compilemessages` |

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
