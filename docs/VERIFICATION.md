# Verification — 7 October 2026

Environment: macOS, Python 3.14.4, Django 5.2.18, psycopg 3.3.6, dedicated local PostgreSQL cluster. All data used for review is synthetic.

## Automated evidence

`python manage.py test books --noinput`: **23 tests passed**.

Covered scenarios:

- All six voucher types reconcile quantity, stock value, balanced journal effects and perpetual COGS.
- Decimal half-up rounding and rejection of tampered client totals, floats, nonfinite values and invalid precision.
- Exact duplicate submissions produce one voucher; key reuse with different data fails.
- Overselling and invalid backdated changes leave all financial, stock, audit, revision and idempotency data unchanged.
- Injected failure during audit insertion rolls back the complete posting.
- Backdated purchases and edited costs recalculate later COGS and stock, retaining old calculation runs and revisions.
- Stale versions are rejected.
- Partial returns use source cost, enforce original rates and quantities, and block a fractional-paise over-refund.
- Linked reversals preserve originals and are retry-safe. Sources with active returns cannot be reversed until returns are reversed.
- Foreign workspace masters/vouchers/ledger/stock queries are rejected. Database trigger also rejects a foreign-account journal entry.
- Append-only audit, revision, calculation, journal, movement and mutation rows reject both UPDATE and DELETE.
- Report opening/closing balances and dashboard reversal totals agree with source fixtures.
- CSV export includes generation metadata and logs the export.
- Signup/login/logout, anonymous access, CSRF and response security headers.
- Two concurrent identical requests produce one posting; two simultaneous sales cannot oversell available stock. These use actual PostgreSQL threads/connections, not SQLite.

`python manage.py check`: no issues.

`python manage.py makemigrations --check --dry-run`: no changes detected.

`node --check books/static/books/app.js`: passed.

## Browser review

Chrome on macOS, default desktop viewport and a 390 × 844 mobile viewport:

- Signed into the synthetic Mogra Trading demo.
- Reviewed populated dashboard and its six voucher shortcuts.
- Posted a ₹125.50 payment; reviewed balanced debit/credit lines in its detail screen.
- Corrected the payment to ₹130.50 with a required reason; dashboard cash and voucher values updated.
- Switched to a sales draft at mobile width; verified the item, quantity and rate controls.
- Entered draft narration, reloaded, reopened the form and verified type/narration survived.
- Posted a ₹480.00 sale from the recovered draft; stock value decreased by ₹333.33.
- Reversed that sale through the explicit confirmation form; stock value returned to ₹70,200.00, with a separate linked REV record.
- Fixed dashboard date-control wrapping and a mobile summary-card overflow. Rechecked document width = viewport width = 390 pixels on the dashboard.
- Restored the normal browser viewport and left the demo dashboard open.

The demo now includes these test transactions and their history; it is not intended as real business data.

## Not verified

No 1,000-user or sustained performance test; no browser matrix beyond Chrome; no physical Android/iOS or Windows test; no native binaries; no backup/restore/RPO/RTO evidence; no full security/dependency audit; no full accessibility audit. No statement of NFR compliance is made. Mobile dashboard/form checks are not a substitute for a complete responsive book/table acceptance matrix.
