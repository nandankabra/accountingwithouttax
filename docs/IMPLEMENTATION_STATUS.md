# Implementation status — 8 October 2026

**Working local development build. The complete report is not 100% implemented or accepted for production.**

The source report is preserved. The owner confirmed perpetual inventory, moving weighted average and blocking negative stock. Numbering, quantity precision, return rounding and retention remain provisional/pending owner review. PDF export was explicitly requested and is implemented.

| Area | Implemented and locally verified | Remaining work |
|---|---|---|
| Platform | Responsive web app; Chrome desktop and 390-pixel viewport review; Windows x64 EXE and Apple Silicon/Intel DMGs built; packaged Mac key activation verified | Windows installation/signing/acceptance; macOS trusted signing/notarization; native Android/iOS; latest-two-version browser and physical-device matrix |
| Accounting integrity | Six voucher types; opening account/item balances; atomic balanced posting; exact totals; idempotency; stale edits; linked reversals; immutable history | Value-only adjustments; accounting-owner acceptance; representative large histories |
| Inventory | Perpetual moving average; source-cost returns; negative-stock blocking; deterministic backdated replay; partial-return reversal regression | Approve units/precision/rounding policies; replace full-history materialization with checkpoints/affected-suffix calculations |
| Books/dashboard | Period summaries; dated ledger/stock opening and closing; voucher drill-through; combined cash/bank ledger; paginated books/masters; searchable bounded form selectors; voucher and book search/filter/sort | Independent dashboard widget failure handling; complete field-adjacent validation and accessibility review |
| Security | Argon2; sessions; CSRF; ownership checks; CSP; shared database login/reset throttling; password change; single-use reset; other-session invalidation | Real SMTP delivery; least-privilege production DB roles; external security review; unresolved desktop build-tool advisory and release pipeline; proxy/log review |
| Company/subscriptions | Editable company contact details; provider-only customer/password provisioning; manual plan/status/expiry/renewal; provider-issued keys, activation and revocation; expired read/export access | Automatic billing if selected; commercial hosting, signing and customer acceptance |
| Audit | Login/logout/failures; password change/reset; master/post/edit/reverse/export and company/subscription events; append-only DB triggers and revisions | Rejected-action/deletion-attempt coverage; production operator access review |
| Drafts | Workspace-scoped browser drafts; recovered draft tested; exact-payload/key retry when outcome uncertain | Multi-tab draft conflicts; cross-device interruption matrix; native device storage |
| Exports | Ledger, inventory and item-wise vouchers CSV; metadata; source IDs/status/version; formula neutralization; 5,000-row CSV caps; private PDFs for all voucher types; WhatsApp review and optional system file sharing | Excel if selected; import and round-trip acceptance fixtures |
| Capacity | 1,000 synthetic authenticated users, 8,000 HTTPS requests, reconciliation checks; timing instrumentation and repeatable harness | Latency target acceptance; representative history and sustained/production tests; CPU/memory/connection monitoring and query profiling |
| Recovery | Streaming encrypted full backup; authentication/tamper tests; separate local restore with matching financial tables; daily Linux timer/failure-log templates | Install production schedule; off-host storage and keys; delivered alerts; continuous WAL/PITR for 15-minute RPO; representative 4-hour RTO drill |
| Operations | Versioned migrations; structured UTC request timestamps, routes, IDs and timings; production config checks | Staging/production environments; CI/CD; full health/metrics/alerts; availability evidence; maintenance workflow |
| Retention | Posted accounting/history protected against application deletion; no backup pruning | Owner-approved accounting/audit/backup retention and storage plan |

## Next work

1. Profile queueing, TLS, sessions and posting under representative history; implement replay checkpoints with reconciliation fixtures.
2. Finish web acceptance: value-only adjustments, field errors, draft conflicts and resilience.
3. Establish staging deployment, restricted roles, off-host full backups plus WAL/PITR, monitoring and actual recovery exercises.
4. Validate the built Windows installer on Windows, enable signing, and complete required desktop/mobile acceptance against the shared service.
5. Complete security, accessibility, device/browser and accounting-owner release acceptance.

Local tests and small-fixture recovery evidence do not establish monthly availability, production disaster recovery or cross-platform acceptance. See [verification](VERIFICATION.md) and [operations](OPERATIONS.md) for concrete evidence and its limits.

The current requested feature milestone has 77 passing Django tests and three desktop policy tests. See [client demo](CLIENT_SETUP.md) and [delivery checklist](RELEASE_CHECKLIST.md). A passing local test suite is not a claim of 100% testing or production compliance.
