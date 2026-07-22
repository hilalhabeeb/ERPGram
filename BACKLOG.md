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
- **Amount in words on the printed invoice** — a common GCC requirement ERPNext
  provides; we do not yet.
- **Per-line discount** — invoice-level discount exists; ERPNext/Odoo also allow
  a discount % per line.
- **Payment allocation across invoices** — a payment is recorded against one
  invoice. ERPNext's Payment Entry can settle several at once; worth it once an
  agency runs monthly statements.

## Frappe / Odoo parity — invoicing

The items grid is now an inline child table (add row, edit cells, delete, live
totals, one save), matching how both do line items. Remaining gaps, ranked:

- **Row reordering** — Frappe lets you drag rows to set the order. Ours has a
  `sort_order` and saves in table order, but there is no drag handle yet.
- **UOM / quantity semantics** — every line is qty × rate today. Fine for
  services; if goods ever appear (uniforms, kits) they will want a unit.
- **Keyboard entry** — Frappe adds a row on Enter/Tab from the last cell and is
  fully keyboard-drivable. Ours needs the mouse for "Add row".
- **Live discount + grand-total on the grid** — the grid previews subtotal/tax/
  total live, but the invoice-level discount is edited in a separate card, so a
  discount change only shows after save. Consider folding discount into the grid.
- **Number/currency formatting in inputs** — rates show raw (`450.000`); Frappe
  formats with the currency's precision as you leave the cell.
- **"Fetch from" defaults** — Frappe pulls an item's description/rate and can
  also pull tax templates. We pull description/rate/taxability; a full tax
  *template* (multiple tax rows) is not modelled — one rate per line for now.
- **Stock/GL posting** — both post to a ledger on submit. We deliberately have no
  GL yet (`Service.income_account` is reserved). That is the big one when real
  accounting is needed, and is its own project.

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
