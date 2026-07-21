# Working on ERPGRAM

Read this before changing anything. It is the short version of what previous
work learned the hard way — most items exist because something broke.

A multi-tenant ERP platform. Shared core (tenancy, auth, roles, UI kit) plus
**domain modules**; the only module built so far is **manpower** — GCC agencies
supplying housemaids, drivers, cooks and carers to household sponsors.

---

## Commands

Everything runs in Docker. `web` (Django + Tailwind) and `db` (Postgres 16).

```bash
docker compose up -d           # start; app on http://localhost:8010
make ci                        # the full gate — run before saying you're done
make test / lint / fmt
make migrate
make seed                      # two generic demo tenants
make seed-manpower             # the domestic-worker agency demo
make messages && make compilemessages
```

Windows: `./tasks.ps1 <same targets>`. Don't pipe PowerShell with `2>&1` — PS 5.1
wraps native stderr in error records and reports a false failure.

**Port is 8010, not 8000** (editors squat on 8000). Override with `WEB_PORT`.

Run one-off commands with the entrypoint bypassed, or it will try to migrate first:

```bash
docker compose run --rm --no-deps --entrypoint sh web -c "uv run python manage.py <cmd>"
```

---

## Architecture in one screen

**Two independent axes. Don't conflate them.**

| | question | where |
| --- | --- | --- |
| **domain** | does this feature exist for this customer? | `apps/core/domains.py` |
| **permission** | may *this user* use it? | `apps/core/permissions.py` |

- `Tenant.domain` is chosen at sign-up. Nav entries, permissions and modules each
  declare `domains=(...)`; `None` means every domain.
- Requesting a module your tenant lacks → **404, not 403**. The feature does not
  exist for you; confirming the URL is real would mislead.
- Permissions are codenames on a per-tenant `Role`. Checked in exactly one place:
  `apps/accounts/permissions.py`.

**Tenant isolation is two layers.**

1. Application — `TenantScopedModel.objects` filters on a `contextvars` tenant.
2. Database — Postgres RLS policies, `FORCE`d, added by `apps/core/db.enable_rls`.

**Layout**

```
apps/core/       domains, permissions catalogue, RLS helper, base models, middleware
apps/tenancy/    Tenant, Company, Branch, Department
apps/accounts/   User, Membership, Role, auth, sign-up
apps/ui/         shell, nav, 12 component partials, template tags
apps/manpower/   the domestic-worker module
```

Business logic lives in `services.py` per app. Views resolve, check permission,
delegate. Type-hint service functions.

---

## Rules that bite

Each of these caused a real bug. Several have tests that will fail if you break them.

### Tenancy / RLS
- **Writing tenant-scoped rows needs a bound tenant.** Outside a request, wrap in
  `activate_tenant(tenant.id)` — the DB rejects an insert with no `app.tenant_id`.
  Prefer making the function bind its own tenant (see `ensure_tenant_defaults`)
  rather than trusting callers.
- RLS policies use `NULLIF(current_setting('app.tenant_id', true), '')::uuid`.
  Once that GUC has been `SET LOCAL` on a connection, Postgres reports it as `''`,
  and `''::uuid` raises — on a pooled connection that is a 500, not an empty list.
- The app's DB role must **not** be superuser or `BYPASSRLS`, or policies are
  silently ignored. CI asserts this.
- **`Membership` and `Role` are deliberately NOT tenant-scoped.** They are read
  outside a bound tenant (login, tenant switcher, back office), where RLS would
  hide the rows needed to decide where the user may go. They filter on `tenant`
  explicitly instead.
- M2M join tables have no tenant column, so RLS cannot protect them. Re-check
  ownership in the service (see `_set_worker_relations`).

### Permissions
- A tenant **owner** implicitly holds every permission in their domain. Without
  it, an owner could edit roles until nobody could administer the tenant.
- The Owner role cannot be weakened; an owner's role cannot be changed away.
- Role permissions are JSON, so always intersect with the catalogue on read —
  a stale or hand-edited codename must never grant anything.
- Never advertise what a user cannot reach: filter nav and hide actions.

### Templates
- **`{# ... #}` must open and close on one line.** Multi-line is not a comment in
  Django — it renders as text on the page. Use `{% comment %}`. This shipped
  twice; `tests/test_template_hygiene.py` now enforces it.
- **RTL is non-negotiable.** Logical properties only — `ms-/me-/ps-/pe-/start-/end-`,
  never `ml-/mr-/pl-/pr-/left-/right-`. Same test enforces it.
- Icons must be vendored in `apps/ui/icons/`. A missing one renders an invisible
  placeholder; `tests/test_icons.py` fails the build instead. Pass icon names as
  **keyword** args in Python (`icon="users"`) so the scanner finds them.
- Money on documents: wrap in `{% localize off %}`. The `ar` locale swaps the
  decimal separator and `450.000` becomes `450,000` — ambiguous on an invoice.
- Screenshots with `fullPage: true` misplace `position: fixed` elements. RTL will
  look broken when it isn't. Measure computed styles before "fixing" layout.

### Translations
- Every user-facing string wrapped; `make messages` then translate `locale/ar`.
- **`makemessages` marks guessed translations `fuzzy`, and gettext ignores fuzzy
  entries** — the string renders in English despite looking translated. Clear the
  flag when filling one in.
- Arabic has **six plural forms**; fill all `msgstr[0..5]`.
- **Do not edit `.po` files through a shell heredoc.** It mangles the backslash
  escapes and has corrupted the header before. Write a script file instead.
- Brand names are not translatable strings.

### General
- **Ask before adding a dependency.** `add_months()` is hand-rolled rather than
  pulling in python-dateutil for one call.
- Snapshot data onto financial records (`Placement.worker_name`) — an invoice must
  keep saying what was agreed after someone renames things.
- Derive totals from their lines; a stored total is one edit away from lying.
- Don't ship a button wired to `#`.

---

## Testing

- `pytest`, `factory-boy`. Target critical paths, not coverage.
- Tenant-scoped reads in tests need `activate_tenant(...)` too.
- **`SET LOCAL` survives to the end of the surrounding transaction**, and in tests
  that is the whole test — so after one `activate_tenant(A)`, a later read still
  sees tenant A unless you bind again. This has produced confusing failures.
- Prove isolation at **both** layers (ORM and raw SQL) for anything new.
- Rendering a form is not evidence it works. POST it. An invite bug survived a
  release because only the modal was screenshotted.

## Definition of done

`make ci` green (ruff, format, missing-migration check, Django checks, tests),
then **drive the actual page in a browser**. Tests passing is not proof the screen
renders.

See [BACKLOG.md](BACKLOG.md) for what is planned next.
