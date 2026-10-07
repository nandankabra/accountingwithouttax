# Simple Books — first working development milestone

A local, responsive accounting app based on `Simple_Accounting_System_NFR_Report.md`. Built on Django 5.2, PostgreSQL, and browser JavaScript, with one authoritative posting service shared by its web screens and JSON endpoints.

**This is a development build, not a production/NFR-compliant release.** No deployment or real financial data is required to review it. The source NFR report is preserved unchanged.

## Run locally

Requires Python 3.12+ and PostgreSQL 16+. On this Mac:

```sh
cd /Users/nandankabra/ondemand/accountingwithouttax
/opt/homebrew/bin/python3 scripts/dev.py
```

Open <http://127.0.0.1:8017/> and create a workspace. The script installs pinned dependencies, initializes a separate development database under `.runtime/postgres`, runs migrations, and starts Django. This cluster uses port 55439 on a private Unix socket only; it does not connect to or modify the existing PostgreSQL server on port 5432. `.runtime` is private to the local OS user and ignored by Git.

To stop the app, press Ctrl-C. To stop its database:

```sh
pg_ctl -D .runtime/postgres stop
```

For Windows or an existing PostgreSQL instance, create a dedicated empty `simplebooks` database, set the `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, and `PGPASSWORD` environment variables, then create a virtual environment, install `requirements.txt`, and run `python manage.py migrate` and `python manage.py runserver 127.0.0.1:8017`. The `.env.example` documents configuration; it is not automatically loaded. Windows execution remains unverified.

## Try sample books

```sh
.venv/bin/python manage.py seed_demo
```

Choose a local password when prompted and sign in as `demo@example.test`. The command creates a clearly labelled synthetic business with accounts, items, all six voucher types, and traceable stock. It refuses to overwrite an existing user. Supply `--email another@example.test` to create another independent sample. It is disabled outside development.

The browser opened during implementation is signed into this synthetic demo. Create a separate workspace for your own testing.

## Working now

- Single-owner signup, Argon2 password hashing, session login/logout, CSRF protection, configurable idle expiry, workspace-scoped access.
- Dashboard with period summaries for all six voucher types; cash/bank, customer, supplier and stock balances.
- Account and item creation, INR values, quantities to 3 decimal places.
- Payment, receipt, sales, purchase, item-wise credit notes and debit notes.
- Atomic balanced posting; server totals compared with submitted exact-decimal totals; UUID identities and per-type numbering.
- Perpetual stock accounting, moving weighted average, negative-stock blocking.
- Referenced returns, backdated recalculation, version-checked posted edits, linked reversal vouchers.
- Database-protected append-only audit events, revisions, calculation snapshots and idempotency records.
- Ledger and stock books with period opening/closing values, pagination and source-voucher links. Vouchers have search, type filter and date sorting.
- Ledger CSV export with period, organisation, user and generation metadata, capped at 5,000 entries.
- Browser-local voucher drafts and exact-payload retry after uncertain submissions. Posting requires a connection.

## Validation

```sh
.venv/bin/python manage.py test books --noinput
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check --dry-run
node --check books/static/books/app.js
```

Tests use a separate `test_simplebooks` database. The PostgreSQL test role must have permission to create and drop it. The development cluster meets this requirement.

See [verification](docs/VERIFICATION.md), [architecture and accounting rules](docs/ARCHITECTURE.md), [API](docs/API.md), and [remaining work](docs/IMPLEMENTATION_STATUS.md).

## Key limitations

Opening balances, value-only adjustments, PDF/other exports, native clients, backup automation, disaster recovery, monitoring, production identity operations and load testing are not implemented. Do not migrate existing live books into this build. Whole-workspace replay prioritizes correctness during this milestone but is not a validated strategy for large histories; incremental checkpoints and representative load tests are required before scaling claims.

Desktop/mobile native applications and 1,000 simultaneous users remain release requirements. The current app does not claim either. Production configuration forces HTTPS/secure cookies and requires an external secret, but production hosting, a non-owner runtime database role, distributed rate limiting and security review are still needed.
# accountingwithouttax
