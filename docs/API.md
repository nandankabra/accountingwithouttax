# Development JSON API

Same-origin Django session authentication. Sign up/sign in through `/signup/` or `/login/`; POST `/logout/` to revoke the session. Every protected endpoint derives its workspace from the authenticated owner. There is no client-selectable tenant ID. Unsafe requests require the `X-CSRFToken` header matching the CSRF cookie. All financial decimals are JSON strings.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/bootstrap/` | Workspace, identity, today, account/item masters |
| POST | `/api/masters/accounts/` | `{name, kind}` |
| POST | `/api/masters/items/` | `{name, unit}` |
| GET | `/api/dashboard/` | Period totals and balances |
| GET/POST | `/api/vouchers/` | Paginated list / post voucher |
| GET/PUT | `/api/vouchers/<uuid>/` | Current data, history, journal / correction |
| POST | `/api/vouchers/<uuid>/reverse/` | Linked compensating voucher |
| GET | `/api/ledger/?account=<uuid>` | Opening/closing and journal entries |
| GET | `/api/inventory/?item=<uuid>` | Opening/closing and stock movements |
| GET | `/api/audit/` | Paginated audit events |
| GET | `/api/export/ledger.csv?account=<uuid>` | Bounded ledger export; logged |

Date-filtered endpoints accept `start=YYYY-MM-DD&end=YYYY-MM-DD`, defaulting to current month through today. Books/lists accept `page`, with 25 rows per page. Voucher lists also accept `kind`, `q` (narration or full voucher number), and `sort=newest|oldest`. Bootstrap currently returns all masters and requires pagination before large-volume release.

Posting, correction and reversal require an `Idempotency-Key` UUID header. Retain both key and exact payload across a connection failure or timeout. Do not create a new key until the first outcome is resolved. Reusing a key with different content returns 409. Success returns `{id, version, number?, duplicate}`.

Payment/receipt payload:

```json
{"kind":"PAY","date":"2026-10-07","account":"<expense-or-party-uuid>","cash_account":"<cash-or-bank-uuid>","amount":"125.50","expected_total":"125.50","narration":"Office stationery"}
```

Inventory voucher payload:

```json
{"kind":"PUR","date":"2026-10-07","account":"<supplier-uuid>","lines":[{"item":"<item-uuid>","quantity":"10.000","rate":"100.00"}],"expected_total":"1000.00","narration":"Goods received"}
```

Credit/debit notes additionally require `reference` containing the source sale/purchase UUID. Rates, party and items must match it. An edit submits the full voucher plus `version` and a nonempty `reason`. Reversal submits only `{version, date, reason}`. A stale version returns 409; clients must refresh and review before resubmission.

Errors contain `error`, usually `field`, and a support `reference_id`. Authentication failures return 401; inaccessible objects return 404; stale/idempotency conflicts return 409; invalid accounting inputs return 400. Native clients and a versioned OpenAPI contract remain future work.
