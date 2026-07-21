# Backlog

Ideas and known gaps, roughly in the order they are worth doing. Nothing here is
committed to — it is a memory aid, not a plan.

Done so far: version control · tenancy CRUD · roles & permissions · audit columns ·
CI · domains & manpower masters · placements/invoices · biodata sheets.

---

## Next up

- **Production deploy** — the main thing between this and real users. Needs
  `gunicorn`, a production image, `collectstatic`, SMTP, and a non-superuser DB
  role. Today it only runs under `runserver`.
- **Payments on a placement** — currently a single `amount_paid`. Agencies take a
  deposit then a balance, so a payments table with dates and methods is the
  natural follow-up to the invoice.
- **Tenant-level default tax rate** — defaults to 10% (Bahrain). Saudi is 15%,
  UAE 5%. Editable per placement today, but the default should be per tenant.

## Manpower module

- **Replacement / refund flow** — the "one free replacement within three months"
  clause is in the demo T&Cs but nothing models it.
- **Document uploads with expiry reminders** — the model and dashboard warning
  exist; add file upload and a real notification (email or in-app).
- **Sponsor detail page** — a sponsor's placement history, currently only visible
  from the placement side.
- **Worker availability calendar** — who frees up when, from contract end dates.
- **Bilingual occupation/skill names** — they are per-tenant data, so an Arabic
  agency renames them by hand in setup today.
- **Arabic biodata sheet as the default for local sponsors** — the layout already
  mirrors; it is a question of which language the print link opens in.

## Platform

- **Topbar search** is decorative (`url=""`). Wire it once there is enough data to
  search across workers, sponsors and placements.
- **Accessibility pass** — run axe over the main screens; focus rings and labels
  were built in but never audited.
- **Performance pass** — check `select_related` / N+1 on the list pages as data
  grows; add `django-debug-toolbar` in dev.
- **Second domain** to prove the mechanism generalises (retail or construction).
  The registries are built for it; nothing has exercised them but manpower.
- **Soft delete everywhere** — archiving exists on tenancy and manpower masters
  but is not a shared base-model concern yet.
- **Audit log** — `created_by`/`updated_by` answer who, never what changed.

## Smaller / opportunistic

- Invoice numbering separate from placement reference (`PL-0001` doubles as both).
- Bulk actions on the worker list (the data table already renders checkboxes).
- Export to CSV/Excel for worker and placement lists.
- Email the biodata sheet or invoice to a sponsor directly.
- Rate-limit public sign-up; add email verification.
- `django-debug-toolbar` and a `make shell_plus`-style convenience.

## Deliberate non-goals for now

- No DRF/API layer until something needs it — services are written so it can be
  added without a rewrite.
- No Celery/Redis until there is real background work.
- No PDF library; print-styled HTML gives correct Arabic and no dependency.
