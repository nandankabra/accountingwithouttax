# Architecture and accounting rules

## Decisions and provenance

On 7 October 2026 the owner explicitly selected **perpetual inventory, moving weighted average, and blocking negative stock** in this conversation. The report's other proposed defaults remain provisional, including numbering, precision, rounding, return costing, and retention. No tax modules are implemented.

For this development milestone:

- INR amounts and rates use two decimal places. Quantity uses three. All inputs travel as decimal strings; Python `Decimal` performs authoritative arithmetic. Browser totals use scaled `BigInt` values.
- Round each line quantity × rate half-up to a paise; sum rounded lines. Never use binary floats to post money.
- Separate sequential voucher series (PAY, REC, SAL, PUR, CN, DN, REV, OPN), no annual reset or manual numbers. Internal UUIDs are never reused.
- Dates are organisation-local calendar dates (initially Asia/Kolkata); event timestamps are UTC. The timezone is stored on each workspace. Timezone editing is not yet available.
- One unique item per voucher simplifies source-line allocation. Maximum 100 lines. Quantities/rates must be positive; zero quantities/value-only adjustments are not supported.
- Sales and credit notes use customer/cash/bank; purchases and debit notes use supplier/cash/bank. Payment/receipt uses a distinct cash/bank account and a non-system counter-account. System inventory/COGS ledgers cannot be selected to bypass stock posting.
- Masters start at zero. A dedicated OPN record establishes opening account debit/credit amounts and item quantities/values; automatic opening equity balances the entry. Only one OPN record exists per workspace. It is editable with history and cannot be reversed. Its date cannot follow other vouchers; ordinary postings cannot precede it. Zero-cost opening stock is allowed.

## Posting

| Type | Debit | Credit | Stock |
|---|---|---|---|
| Payment | Selected non-system account | Cash/bank | None |
| Receipt | Cash/bank | Selected non-system account | None |
| Purchase | Inventory | Supplier/cash/bank | Quantity and purchase value increase |
| Sale | Customer/cash/bank; COGS | Sales; inventory | Quantity and average cost decrease |
| Credit note | Sales returns; inventory | Customer/cash/bank; COGS | Restore original allocated sale cost |
| Debit note | Supplier/cash/bank | Inventory | Remove original allocated purchase cost; line-rounding residual uses the rounding account |
| Reversal | Original credits | Original debits | Negate source quantity and cost movements |
| Opening balances | Opening debit balances; stock value; balancing equity when needed | Opening credit balances; balancing equity when needed | Establish quantity and value without sales/purchase turnover |

Purchase expense is not posted separately: under perpetual accounting, expense is recognized as COGS on sale. This avoids double-counting purchases and COGS.

Weighted average is derived from remaining stock value / quantity, with full depletion taking the residual value. Partial returns track cumulative returned quantity, allocated cost and settlement amount, so paise sum to the source and reversing an earlier partial return cannot allocate a residual twice. A return must reference an earlier, unreversed voucher of the matching type, use its account/item/rate, and not exceed its remaining returnable quantity. Sales- or purchase-return line amounts that would over/under-refund due to fractional paise allocation are blocked; the operator must combine the returns (reverse an earlier partial note if necessary). Purchase returns/reversals that leave negative value or nonzero value at zero quantity are blocked; subsequent transactions must be corrected first. These edge-case policies need owner review.

## Atomicity, concurrency and history

Every write acquires a PostgreSQL `SELECT FOR UPDATE` lock on that owner's workspace inside a Django transaction. Independent workspaces can post concurrently; writes within one business serialize. Idempotency keys are unique per workspace and paired with a canonical request fingerprint. An already committed immutable result can be read without taking the posting lock; unresolved requests are checked again after locking. A repeated identical request returns the previous result; reuse with different content is a conflict. Posted edits also require the expected integer version.

Posting validates master ownership and amounts, writes a voucher revision, replays current revisions in `(date, opening first, original creation time, UUID)` order, verifies balanced effects and nonnegative stock, writes a new immutable calculation run, switches the workspace's active run, then writes its audit and idempotency result. The whole transaction commits or rolls back.

All historic runs remain available in the database. Reports bind to the active run ID fetched at request start, so a concurrent edit cannot mix old and new journal/stock effects within a report. Original vouchers are preserved on reversal. A voucher with active returns must have those returns reversed before it can be reversed. Reversal records and already-reversed vouchers cannot be edited. Original voucher identities/numbers never change on edit.

PostgreSQL triggers reject UPDATE/DELETE on audit, revision, calculation-run, journal, stock-movement and mutation tables. Additional triggers enforce journal/stock master and voucher tenancy. Application endpoints provide no physical deletion or audit rewriting. Database superusers can bypass database protections; production must use separate migration and restricted runtime roles.

The replay implementation currently scans all vouchers and materializes all journal/stock effects for each mutation. Historical storage grows quadratically with a growing workspace. This deliberate initial implementation makes correctness review transparent, but is unsuitable for large production histories without checkpoints, affected-suffix replay, storage planning and benchmarks.

## Application boundaries

- `books/engine.py`: exact-decimal validation and deterministic accounting replay, independent of Django.
- `books/services.py`: workspace provisioning, locking, idempotency, revision/correction/reversal transaction.
- `books/models.py` and migrations: schema, constraints, append-only and tenancy triggers.
- `books/views.py`: session-authenticated JSON endpoints, reports, CSV export, signup/login.
- `books/account_views.py` and `books/security.py`: password changes, reset tokens, shared row-locked throttles and token-log redaction.
- `ops/encrypted_backup.py`: streaming authenticated full-backup and isolated restore tooling.
- `books/static/books`: responsive interface and draft/retry handling.

The local app needs no external services or cross-origin resources. Development recovery emails are written to a private local directory; production recovery requires configured SMTP. Password changes/reset invalidate other sessions. Reset tokens expire after 15 minutes and links use a configured canonical HTTPS origin. Authentication currently uses Django cookie sessions; native-client authentication will be designed with the native apps rather than treating this browser session contract as final.

Implementation references: [Django transactions](https://docs.djangoproject.com/en/5.2/topics/db/transactions/), [Django 5.2 Python support](https://docs.djangoproject.com/en/5.2/releases/5.2/), [Django security](https://docs.djangoproject.com/en/5.2/topics/security/).

## Company, provider access, subscriptions and sharing

A provider is an active Django superuser; ordinary owners cannot enter provider administration, even with a staff flag. Customer creation atomically provisions a hashed-password owner, company, standard accounts and trial subscription. Provider login uses the same shared throttling as customer login. Public signup is disabled by default outside development.

Company profile saves update only contact/name fields plus a profile version while locking the workspace. Owner saves reject stale profile versions. Provider saves also retain the current financial-run pointer, so changing contact details cannot roll financial reports back to an older run. Company/subscription changes create append-only audit events.

Subscription starts/expiry are inclusive organisation-local dates. Trial/active subscriptions permit writes only within their date window; suspended subscriptions do not. Posting/master creation checks the subscription under the workspace lock, which subscription administration also acquires. Committed idempotent retries remain readable after expiry. Existing workspaces receive a 30-day trial in migration 0007; new workspaces receive a 14-day trial. Renewals are administrator-managed and payments are collected separately. Plan prices/durations are descriptive metadata.

Voucher PDFs are authenticated, private downloads with bounded referenced-master lookups. They include contacts, party/items/totals/status and references; internal accounting-cost lines are omitted from the shared document. Stored revisions remain protected while the voucher detail API/UI omit their list. WhatsApp messages are reviewed before handoff; files use native sharing where supported or manual attachment. No public voucher links or automatic messages are created.

The Windows Electron client shares this session-authenticated service. Its renderer has no Node access, is sandboxed/isolated and cannot navigate or redirect to other origins. Only HTTPS WhatsApp handoffs open externally. The configured server must use HTTPS, except same-PC loopback HTTP demonstrations. Credentials and financial databases are excluded from the package.
