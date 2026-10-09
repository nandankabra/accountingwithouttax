# Simple Books — subscription accounting

A local, responsive accounting app based on `Simple_Accounting_System_NFR_Report.md`. Built on Django 5.2, PostgreSQL, and browser JavaScript, with one authoritative posting service shared by its web screens and JSON endpoints.

The standalone Windows release is version 0.4.0. It includes its own accounting engine and local database; no Mac, PostgreSQL installation, network server or internet is needed for bookkeeping. Windows installation/runtime acceptance remains pending. The source NFR report is preserved unchanged; its hosted-service requirements are a separate scope.

See [Windows local installation](docs/CLIENT_SETUP.md) and [provider licence administration](docs/ADMINISTRATION.md).

## Run locally

Requires Python 3.12+ and PostgreSQL 16+. On this Mac:

```sh
cd /Users/nandankabra/ondemand/accountingwithouttax
/opt/homebrew/bin/python3 scripts/dev.py
```

Open <http://127.0.0.1:8017/> and sign in. Create customer companies through the provider administration panel. The script installs pinned dependencies, initializes a separate development database under `.runtime/postgres`, runs migrations, and starts Django. This cluster uses port 55439 on a private Unix socket only; it does not connect to or modify the existing PostgreSQL server on port 5432. `.runtime` is private to the local OS user and ignored by Git.

For browser access from another device on the same LAN, replace the example IP below with this Mac's current network IP and start the server with an explicit host allowlist:

```sh
ALLOWED_HOSTS=localhost,127.0.0.1,192.168.1.44 /opt/homebrew/bin/python3 scripts/dev.py --host 0.0.0.0
```

Open `http://192.168.1.44:8017/` or `/admin/` from a device on that network. Keep the Mac awake and allow the application through the firewall if your organisation's policy permits. This is local-network browser access, not a public deployment. The desktop installers and remote subscription keys still require a reachable trusted HTTPS origin; LAN HTTP does not change that policy.

To stop the app, press Ctrl-C. To stop its database:

```sh
pg_ctl -D .runtime/postgres stop
```

## Standalone Windows app

Use `output/desktop/SimpleBooks-Local-Setup-0.4.0-x64.exe`. The installer includes Python, Django, the posting engine, PDF fonts and a SQLite database engine. Data is created in the current Windows user's `%APPDATA%\SimpleBooksLocal`; no customer data, credentials or provider signing key is bundled.

The app starts a private service on an assigned loopback port retained across restarts to preserve local drafts and shuts it down on exit. A per-launch secret keeps ordinary browser tabs and other network devices out. Money is stored as integer paise and quantities as integer thousandths, with Decimal calculations and protected accounting history. Local writes use immediate transactions and a single request worker.

Copy the installation ID shown at first launch. In the provider admin panel create the customer, save an active subscription with its start/expiry dates, then choose **Generate offline key for a Windows PC**. Enter the installation ID and send the signed `SB2` key privately. Renewal requires a new offline key for the same installation; it preserves the local books. Expired subscriptions retain read/export access and block posting/master creation. Remote suspension is unavailable offline.

The provider signing key is `.runtime/offline-signing.pem` (or `SIMPLEBOOKS_SIGNING_KEY`). Back it up privately: losing/replacing it prevents renewing previously distributed installers. Never distribute it to clients. Public verification material is bundled in the installer.

Accounting and PDFs work offline. WhatsApp opens the user's WhatsApp/browser and requires internet; PDF attachment is manual where the device share sheet is unavailable. The Simple Books menu provides company backup/restore and the local data folder. Startup also retains 30 recent database snapshots. Keep exported backups and installation.json on another drive.

Build and verify on this Mac:

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python scripts/build_windows_local.py --prepare-only
.venv/bin/python scripts/verify.py
.venv/bin/python scripts/build_windows_local.py
node scripts/verify_windows_payload.cjs
```

The former 0.3.0 EXE and DMGs are connected-server clients and are not the standalone Windows release. Packages are unsigned; this Mac cannot verify execution of the Windows installer.

## Working now

- One owner per company, provider administration, subscription-key activation, Argon2 hashing, session login/logout, CSRF protection, configurable idle expiry and workspace-scoped access.
- Editable company name, mobile, company email, address, city and postal code; concurrent updates are checked.
- Provider-created customers with passwords; plan prices/durations, trial/active/suspended status and manual subscription expiry/renewal and provider-issued activation keys. Expired access retains reading and exports.
- PDF download and WhatsApp review/share controls for all eight voucher types. File attachment uses the device share sheet where supported or manual attachment in WhatsApp.
- Voucher detail omits revision-history lists; protected accounting history remains in the database.
- Standalone Windows x64 installer with offline activation/renewal and local backup/restore; Windows runtime acceptance pending. Previous Mac DMGs remain connected clients.
- Password change, single-use email reset links and shared PostgreSQL login/reset throttling. Development reset emails stay on this machine.
- Dashboard with period summaries for all six voucher types; cash/bank, customer, supplier and stock balances.
- Account and item creation, INR values, quantities to 3 decimal places.
- Editable opening account and stock balances, with automatic balancing equity and retained revisions.
- Payment, receipt, sales, purchase, item-wise credit notes and debit notes.
- Atomic balanced posting; server totals compared with submitted exact-decimal totals; UUID identities and per-type numbering.
- Perpetual stock accounting, moving weighted average, negative-stock blocking.
- Referenced returns, backdated recalculation, version-checked posted edits, linked reversal vouchers.
- Database-protected append-only audit events, revisions, calculation snapshots and idempotency records.
- Ledger and stock books with period opening/closing values, pagination and source-voucher links. Vouchers have search, type filter and date sorting; books have movement search, direction filters and date sorting.
- Paginated accounts/items and server-searchable selectors; drafts and corrections resolve selected masters beyond the first page.
- Ledger, inventory and item-wise voucher CSV exports with period, organisation, user and generation metadata, capped at 5,000 rows.
- Encrypted full-backup, authentication and safe restore tooling; daily Linux scheduling templates.
- Browser-local voucher drafts and exact-payload retry after uncertain submissions. Standalone posting uses the bundled local service; the hosted edition requires a server connection.

## Validation

```sh
.venv/bin/python scripts/verify.py
.venv/bin/python scripts/preview_vouchers.py
```

The development bootstrap installs `requirements-dev.txt`; a manually prepared test environment must install it too. Tests use a separate `test_simplebooks` database. The PostgreSQL test role must have permission to create and drop it. The development cluster meets this requirement.

See [verification](docs/VERIFICATION.md), [architecture and accounting rules](docs/ARCHITECTURE.md), [API](docs/API.md), and [remaining work](docs/IMPLEMENTATION_STATUS.md).

## Key limitations

Value-only adjustments, offline accounting, automatic subscription billing, native mobile clients and production operation remain unfinished. The Windows package is unsigned and needs a reachable shared server plus acceptance on a Windows PC. Encrypted full backups and a local restore are verified; continuous WAL/PITR, off-host storage and alert delivery still need deployment and recovery drills. Whole-workspace replay retains all calculation snapshots and grows quadratically in storage; representative history benchmarks and checkpoints are required before scaling claims.

A synthetic 1,000-user HTTPS workload is available through `scripts/loadtest.py`; see the exact results and limits in [verification](docs/VERIFICATION.md). It uses pre-issued sessions and very small books, so production capacity remains unverified. Production configuration requires HTTPS, an external secret and SMTP recovery configuration. Production hosting, restricted database roles, security review, unresolved desktop build-tool advisories and cross-platform acceptance remain release gates. See the [delivery checklist](docs/RELEASE_CHECKLIST.md).

See [backup and account-security operations](docs/OPERATIONS.md) for commands and remaining recovery work.
