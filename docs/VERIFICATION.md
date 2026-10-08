# Verification — updated 8 October 2026

Environment: macOS, Python 3.14.4, Django 5.2.18, psycopg 3.3.6, dedicated local PostgreSQL cluster. Automated tests and PDF layout fixtures are synthetic; existing demo books may also contain later owner-entered records.

## Automated evidence

`python manage.py test books --noinput`: **66 tests passed**.

Covered scenarios:

- All six voucher types reconcile quantity, stock value, balanced journal effects and perpetual COGS.
- Decimal half-up rounding and rejection of tampered client totals, floats, nonfinite values and invalid precision.
- Exact duplicate submissions produce one voucher; key reuse with different data fails.
- Overselling and invalid backdated changes leave all financial, stock, audit, revision and idempotency data unchanged.
- Injected failure during audit insertion rolls back the complete posting.
- Backdated purchases and edited costs recalculate later COGS and stock, retaining old calculation runs and revisions.
- Stale versions are rejected.
- Partial returns use source cost, enforce original rates and quantities, and block fractional-paise settlement mismatches. Reversing an earlier partial return preserves already allocated cost/amount residuals.
- Linked reversals preserve originals and are retry-safe. Sources with active returns cannot be reversed until returns are reversed.
- Foreign workspace masters/vouchers/ledger/stock queries are rejected. Database trigger also rejects a foreign-account journal entry.
- Append-only audit, revision, calculation, journal, movement and mutation rows reject both UPDATE and DELETE.
- Report opening/closing balances and dashboard reversal totals agree with source fixtures.
- Opening account and item balances balance through equity without sales/purchase turnover; date restrictions, same-day precedence, zero-cost stock, edit replay and rollback are tested.
- Ledger, inventory and item-wise voucher CSV exports preserve metadata, IDs, versions and precision, neutralize textual spreadsheet formulas and enforce tenant isolation. Combined cash/bank drill-through reconciles.
- Password change validates the old password and invalidates other sessions; reset is single-use, produces generic replies and revokes old sessions. Shared PostgreSQL throttles limit concurrent login/reset attempts.
- Backup encryption round trips with fresh nonces; tampered ciphertext and wrong keys fail without leaving plaintext output; restore refuses source/system targets. Reset-token log redaction is tested.
- Book filters preserve complete period totals; newest filtered ledger CSV includes intervening hidden movements in running balances. Inventory filters preserve closing stock and historical row balances.
- Master bootstrap/pages are bounded; exact-ID lookup resolves masters beyond the first page and cannot expose another workspace.
- Signup/login/logout, anonymous access, CSRF and response security headers.
- Two concurrent identical requests produce one posting; two simultaneous sales cannot oversell available stock. These use actual PostgreSQL threads/connections, not SQLite.

`python manage.py check`: no issues.

`python manage.py makemigrations --check --dry-run`: no changes detected.

`node --check books/static/books/app.js`: passed.

`manage.py check --deploy`: no issues with explicit test production configuration (HTTPS origin, randomly generated secret, configured dummy SMTP hostname and sender). No SMTP connection or public deployment was performed.

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
- Added opening cash and cotton-bag stock, then corrected cash to ₹1,100 with a reason; version 2 and subsequent weighted costs were preserved.
- Downloaded inventory CSV and checked opening stock, seven movements and the final reversal against closing 127 bags / ₹42,068.75.
- Converted mobile tables into labelled rows; measured inventory document width 390 pixels and table content width 356 pixels without overflow. Mobile book summaries use two columns and a full-width closing balance.
- Reviewed account-security navigation and the password-change form. Credentials were tested through isolated Django clients.
- Searched the cash ledger for PAY-000003 and displayed only the ₹130.50 payment while full closing cash stayed ₹2,469.50. Downloaded its filtered CSV and verified one matching payment, ₹130.50 credit and full-period closing ₹2,469.50. Screenshot: `.runtime/book-search-desktop.jpg`.
- Searched master names through the new server lookup and master-list controls.
- Checked filtered ledger at 390 pixels: document width 390, table width 356; restored normal viewport and left the synthetic demo open.
- Client asset hashes now change on CSS/JS updates so a cached older client is not loaded after a correction.

The initial demo and agent test transactions are synthetic. Preserve later owner-entered records and treat the workspace as private.

## Encrypted backup and restore

On 7 October 2026, the local synthetic workspace was streamed into an encrypted full backup, authenticated and restored into a new database. It contained 12 vouchers, 14 revisions and 19 audit events. Complete-row fingerprints and counts matched across eight financial tables. Restore took 0.148 seconds for this small fixture. `.runtime/restore-evidence.json` retains the machine-readable result.

This verifies local full-backup recovery. Daily Linux timer/failure-log templates are present but not installed. Off-host storage, independently recoverable keys, delivered alerts, continuous WAL/PITR, retention and representative RPO/RTO drills remain open.

## Synthetic capacity evidence

The repeatable harness runs a new database and a separate loopback HTTPS Gunicorn service, leaving the demo books untouched. Each of 1,000 independent workspaces starts with three vouchers and one item. Pre-issued authenticated sessions perform bootstrap, dashboard, voucher search, ledger, sale, duplicate retry, receipt and stock lookup. Users arrive over five seconds, with two-second think time between most actions. Login/password hashing, static assets, browser rendering and large histories are excluded.

All three full runs completed 8,000 HTTP requests with zero request failures and zero wrong-workspace, duplicate, journal-balance or stock-value failures. Each ended with 5,000 vouchers and 5,000 mutation records. The latency targets **did not pass**.

| Run | Worker/thread configuration | Peak requests in flight | Normal API p95 | Dashboard p95 | Ledger p95 | Posting p95 | Retry p95 |
|---|---|---:|---:|---:|---:|---:|---:|
| Initial | 4 Gunicorn gthread workers × 8 threads | 559 | 0.073 s | 0.006 s | 2.816 s | 3.033 s | 3.303 s |
| Eight-worker comparison | 8 Gunicorn gthread workers × 8 threads | 612 | 1.127 s | 0.363 s | 3.539 s | 3.319 s | 3.438 s |
| Instrumented repeat | 4 Gunicorn gthread workers × 8 threads | 791 | 3.364 s | 0.636 s | 7.841 s | 6.687 s | 7.315 s |

The instrumented repeat measured application-handler p95 of 21.97 ms for posting and 6.19 ms for ledger, while client response times were much higher. The handler measurement excludes server queueing, TLS transport, outer session middleware and client scheduling. It indicates where to investigate; it does not establish the cause or replace end-to-end latency acceptance. More application workers alone did not resolve the target.

Run the same test:

```sh
.venv/bin/python scripts/loadtest.py --users 1000 --workers 4 --threads 8 --think-seconds 2
```

Use `--users 10 --think-seconds 0.1` for harness smoke testing. A failed latency/reconciliation result exits nonzero. Private `.runtime/load_*/result.json` files retain metrics; test databases and owner-readable session/TLS fixtures are retained for diagnosis. No fixtures contain production credentials. The script limits worker threads to preserve the local database connection budget.

The active-user counter includes arrivals waiting on the ramp/think timer. The separate in-flight count shows actual overlapping requests. This brief small-book workload is preliminary evidence, and requires agreed data volumes, sustained tests, deployment sizing and production monitoring before PERF requirements can be accepted.

## Not verified

Windows execution/installation/signing and physical Android/iOS; latest-two-version browser matrix; representative-history or sustained production capacity; off-host WAL/PITR and production RPO/RTO; real SMTP and alert delivery; monthly availability; external security review and unresolved desktop build-tool advisory; full accessibility/usability acceptance. Owner approval of unresolved accounting/export/retention defaults remains outstanding. No statement of complete NFR compliance is made.

## Requested delivery features — 8 October 2026

- 13 additional Django tests cover company update validation/isolation/stale versions, provider-only access, rate-limited provider login, password/account provisioning, subscription expiry/suspension/renewal/read access, private PDFs for all eight types, revision-list removal, escaped markup, 100-line PDF pagination and preservation of a newer financial run during provider profile saves.
- `node --test desktop/policy.test.cjs`: two tests pass for allowed server origins and WhatsApp-only external links.
- `scripts/verify.py` passes Django checks, migration drift, installed dependency consistency, client/desktop syntax, desktop policy tests and all 66 Django tests. Results are retained in private `.runtime/release-checks.json` and `.runtime/release-checks.log`.
- Chrome review: owner voucher has PDF/WhatsApp actions and no revision list/version badge; PDF button downloaded PAY-000003; WhatsApp dialog shows editable text, optional recipient, native file-share control and invalid-phone error. No WhatsApp message was sent. Company form exposes all six editable contact fields. Provider home, customer-add form and plan/status/expiry controls render correctly.
- Desktop development wrapper on macOS connected through its setup screen and signed into the existing demo. Windows x64 NSIS installer built successfully with branded executable metadata and icon. Package inventory contains only the desktop client files/icon, with no database, credentials or runtime node_modules. Source equality, x64 PE header and SHA-256 are checked; `output/desktop/release-manifest.json` retains evidence. The Windows installer itself was not executed.
- All eight synthetic voucher layouts were rendered/reviewed, including a seven-page 100-line document with repeated headers and final totals. `scripts/preview_vouchers.py` creates these without database reads/writes; the combined sample is `output/pdf/simplebooks-voucher-demo.pdf`.
- `pip-audit` on runtime requirements found three unique advisories in cryptography 48.0.1 (reported twice each). Upgraded/pinned cryptography 50.0.2, reran tests and repeated scan: no known vulnerabilities. Python PDF QA tools are in development requirements only.
- `npm audit --omit=dev`: no findings. Full npm audit: eight moderate affected development entries caused by the unpatched `sprintf-js` precision-specifier denial-of-service advisory. These build packages are not shipped inside the desktop client. This npm scan does not assess bundled Electron/Chromium security or replace independent review. No force/downgrade fix was applied.

[Client demo guide](CLIENT_DEMO.md) and [delivery checklist](RELEASE_CHECKLIST.md) identify Windows, hosting, real-message delivery, signing, performance and recovery gates. The full NFR report remains unaccepted for production.

After the cryptography update, a new encrypted full backup was restored into a new local database on 8 October. All 23 public tables matched complete-row SHA-256 fingerprints and counts, including users, company profiles, plans and subscriptions. The source was unchanged during verification. The small fixture contained 17 vouchers, 19 revisions and 38 audit events; restore took 0.174 seconds. Evidence: `.runtime/delivery-restore-evidence.json`. This remains a local small-fixture drill, not production RPO/RTO evidence.

The company form, provider home and WhatsApp dialog were reviewed at 390 × 844: document width was 390 pixels, and the sharing dialog width was 362 pixels. The default viewport was restored afterward.
