# Implementation status

Commands: `./run dev` · `./run test` · `./run prod` · `./run migrate` · `./run seed` (Windows: `python run dev`).
Demo logins after seed: 09120000001/admin123 (admin), 09120000002/staff123, 09120000003/customer123.
Maintenance CLI: `flask expire-orders`, `flask reconcile-payments`, `flask sms-retry`, `flask send-marketing <id> "<text>"` (run the first three from cron).

## Done (verified by 31 automated tests + manual smoke runs of dev/prod modes)
- Migrations: 0001 baseline (old schema) -> 0002 (catalog/variants/orders/payments/SMS, data backfilled) -> 0003 (banners, auto-scroll). Unversioned legacy DBs are stamped then upgraded; SQLite is backed up first.
- Products: variants (relational, per-variant stock/SKU/price), options with stable ids, multi-image (order/primary/alt, validated uploads), tags, attributes, draft/published/archived, safe delete (archive if ordered).
- Categories: unlimited-depth tree (materialized path), cycle prevention, internal/hidden categories never leak; /categories tree page; breadcrumbs; recursive menu.
- Search/filter: name, description, SKU, brand, tags, attributes; tag/attribute/option/price/stock filters combine; sort; pagination; filter chips; mobile filter drawer.
- Homepage: Banner model (links to product/category/URL), sections from any category (incl. internal) showing newest N as ONE vertically scrolling card, optional auto-scroll per section, title falls back to category name.
- Bulk import/export: .xlsx / .csv (+ Variants sheet), dry run, row-level errors, upsert by SKU.
- Orders: pending/preparing/shipped/received/cancelled/failed, status history with staff, reservation -> deduction -> restore, CAS-guarded transitions, coupons, shipping methods, address book, snapshots.
- SMS (Kavenegar + mock adapter, templates, OTP limits, idempotent log, retries, consent/opt-out) and Zarinpal v4 (+ mock gateway, duplicate-callback protection, server-side verify, expiry/reconcile).
- Store settings, coupons, shipping, wishlist, reviews, sitemap/robots/meta tags, CSRF on all forms, role permissions.

## Not verified / limits
- Kavenegar and Zarinpal were only tested against mocks (no credentials). Kavenegar error-code retry classification is my reading of their docs.
- Layout/scroller/responsive CSS was not checked in a real browser or on real devices.
- Search uses LIKE (no full-text index); fine for thousands of products, not hundreds of thousands.
- Zarinpal needs store currency IRT/IRR (set in Store settings); default stays USD, so only pay-on-delivery is offered until changed.
- Permissions are role-based (staff/admin), not per-user.

## Update 2 (language/RTL, category filter, horizontal sliders, fixes)
- Store settings -> "Website language" (English LTR / فارسی RTL) switches text, `dir`, Bootstrap RTL CSS and the Persian font for the whole site (storefront, login/register, staff panel). Translations live in `app/i18n.py` (`FA` dict, missing strings fall back to English). Add a language = one entry in `LANGUAGES` + one dict.
  Not translated: validation messages from WTForms, dynamic messages built with f-strings, month names, the Flask-Admin DB panel, and your own product/category text.
- Filter sidebar has a Categories tree (any depth); the current category is pre-ticked, its ancestors are expanded; multiple categories combine (OR); ticking a child unticks its parent.
- Homepage sections and the banner slider scroll horizontally, follow RTL, auto-scroll only while on screen.
- Fixed: UndefinedError on product add/edit (regression test added); clipped card content in sections; double scrollbar (html/body height + overflow rules); dark-mode sidebar/pill highlight contrast.
