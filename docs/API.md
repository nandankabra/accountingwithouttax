# Development JSON API

Same-origin Django session authentication. Sign up/sign in through `/signup/` or `/login/`; POST `/logout/` to revoke the session. Every protected endpoint derives its workspace from the authenticated owner. There is no client-selectable tenant ID. Unsafe requests require the `X-CSRFToken` header matching the CSRF cookie. All financial decimals are JSON strings.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/bootstrap/` | Workspace, identity, today, account/item masters |
| GET/POST | `/api/masters/accounts/` | Paginated lookup / `{name, kind}` |
| GET/POST | `/api/masters/items/` | Paginated lookup / `{name, unit}` |
| GET | `/api/opening/` | Existing opening voucher or null |
| GET | `/api/dashboard/` | Period totals and balances |
| GET/POST | `/api/vouchers/` | Paginated list / post voucher |
| GET/PUT | `/api/vouchers/<uuid>/` | Current data, journal / correction |
| GET | `/api/vouchers/<uuid>/pdf/` | Private voucher PDF download; logged |
| POST | `/api/vouchers/<uuid>/reverse/` | Linked compensating voucher |
| GET | `/api/ledger/?account=<uuid>` | Opening/closing and journal entries |
| GET | `/api/inventory/?item=<uuid>` | Opening/closing and stock movements |
| GET | `/api/audit/` | Paginated audit events |
| GET | `/api/export/ledger.csv?account=<uuid>` | Bounded ledger export; logged |
| GET | `/api/export/inventory.csv?item=<uuid>` | Bounded stock movement export; logged |
| GET | `/api/export/vouchers.csv` | Bounded item-wise voucher export; logged |

Date-filtered endpoints accept `start=YYYY-MM-DD&end=YYYY-MM-DD`, defaulting to current month through today. Books/lists accept `page`, with 25 rows per page. Voucher lists also accept `kind`, `q` (narration or full voucher number), and `sort=newest|oldest`. Ledger and ledger CSV also accept `account=cash-bank` for the combined cash/bank drill-through; every row identifies its account. Voucher CSV accepts the voucher filters and caps expanded item/account rows at 5,000. Bootstrap returns only the first 25 accounts and 25 items, plus `default_cash`. Master GET requests accept `q`, `page`, `sort=name|name-desc`; accounts also accept `kinds` (comma separated) and `non_system=1`. Exact `ids` lookup accepts up to 200 UUIDs and returns only owned matches, allowing drafts and posted edits to resolve masters outside the initial page. Searches and form selectors fetch pages rather than the whole workspace.

Posting, correction and reversal require an `Idempotency-Key` UUID header. Retain both key and exact payload across a connection failure or timeout. Do not create a new key until the first outcome is resolved. Reusing a key with different content returns 409. Success returns `{id, version, number?, duplicate}`.

Payment/receipt payload:

```json
{"kind":"PAY","date":"2026-10-07","account":"<expense-or-party-uuid>","cash_account":"<cash-or-bank-uuid>","amount":"125.50","expected_total":"125.50","narration":"Office stationery"}
```

Inventory voucher payload:

```json
{"kind":"PUR","date":"2026-10-07","account":"<supplier-uuid>","lines":[{"item":"<item-uuid>","quantity":"10.000","rate":"100.00"}],"expected_total":"1000.00","narration":"Goods received"}
```

Opening balances are posted/edited through the same voucher endpoint:

```json
{"kind":"OPN","date":"2026-10-01","balances":[{"account":"<cash-uuid>","side":"debit","amount":"1000.00"}],"lines":[{"item":"<item-uuid>","quantity":"10.000","amount":"3000.00"}],"expected_total":"4000.00"}
```

`expected_total` is the greater of total debits (including stock values) and total credits before balancing equity. System accounts cannot be supplied as opening account rows. The server balances the resulting journal through opening equity. Existing opening records require normal edit version/reason fields.

Credit/debit notes additionally require `reference` containing the source sale/purchase UUID. Rates, party and items must match it. An edit submits the full voucher plus `version` and a nonempty `reason`. Reversal submits only `{version, date, reason}`. A stale version returns 409; clients must refresh and review before resubmission.

Errors contain `error`, usually `field`, and a support `reference_id`. Authentication failures return 401; inaccessible objects return 404; stale/idempotency conflicts return 409; invalid accounting inputs return 400. Native clients and a versioned OpenAPI contract remain future work.

Account recovery uses HTML forms at `/security/`, `/password-reset/` and `/password-reset/confirm/<uidb64>/<token>/`, with CSRF protection. Password change requires the current password; reset requires a single-use emailed token. See [operations](OPERATIONS.md) for canonical origin, mail and throttle configuration.

Ledger and inventory accept `q` (full voucher number, narration or type), `sort=oldest|newest`, and `direction`. Ledger directions are `debit|credit`; inventory directions are `inward|outward`. These filters change visible rows/count and CSV contents; period opening/closing and ledger debit/credit totals always cover the full period. Inventory row balances remain their historical calculation balances. Ledger CSV balances include intervening hidden entries, even when exported newest first, and identifies the full-period closing balance separately. CSV metadata and audit events retain the selected filters. Ledger export requires the complete period to contain at most 5,000 entries so full running balances remain bounded.

Company contact fields are edited through the CSRF-protected HTML form at `/company/`. Bootstrap includes subscription status, plan, start/expiry dates and `can_write`. Inactive subscriptions reject master creation and new posting/edit/reversal with 403; read/export access and already committed idempotent retries remain available. Product administration at `/admin/` requires an active superuser. All administrator logins reuse the shared rate-limited `/login/` flow. Production self-signup defaults off. See [client demo](CLIENT_SETUP.md) for provider setup and manual renewals.

Subscription activation uses GET/POST `/activate/` and CSRF-protected POST `/api/activation/` with `{key}`. Keys carry the configured canonical origin and a random bearer secret; only the secret digest is persisted. Successful activation signs into the owned customer account and rotates the CSRF/session state. Revoked/replaced activated sessions are logged out on their next request. Invalid/expired/suspended/disabled keys are rejected. Provider keys cannot authenticate superusers. Do not put keys in URLs or logs.
