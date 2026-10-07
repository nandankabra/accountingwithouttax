# Implementation status — 7 October 2026

Status: **first working local development milestone; not approved for production**.

The original report remains authoritative for scope. The inventory policy was confirmed in conversation. Other proposed report defaults have not been represented as approved decisions.

| Area | Current evidence | Remaining work |
|---|---|---|
| Platform | Responsive web app; Chrome desktop/mobile viewport review | macOS/Windows installable clients; native Android/iOS; full browser/device matrix |
| Integrity | Six voucher types; balanced atomic posting; retries; tenant validation; server totals; edits/reversals | Opening balances; value-only adjustments; accounting-owner review and larger fixtures |
| Inventory | Perpetual weighted-average; source-cost returns; negative-stock rejection; backdated replay | Agree units/precision/return rounding edge cases; improve replay performance |
| Books/dashboard | Current-period summaries; dated ledger and stock opening/closing; drill-through; paginated books | More sort/search controls; receivable/payable ageing and settlement allocation if requested; independent widget failure isolation |
| Security | Argon2; sessions; CSRF; ownership checks; CSP; append-only DB history; CSRF and IDOR tests | Password reset/change and recovery; shared/distributed login throttling; external audit; dependency scanning and release pipeline; least-privilege runtime DB user |
| Audit | Login/logout/failed-login, masters, post/edit/reverse and ledger export events; immutable revisions/runs | Explicit rejected/deletion-attempt events, expanded security-event coverage, operator access policy |
| Drafts | Workspace-scoped browser local storage; retry original payload/key when outcome uncertain | Multi-tab draft conflict UX; encrypted/native-device draft handling; network interruption acceptance matrix |
| Exports | Ledger CSV with metadata and formula-injection neutralization for text | Owner format decision; voucher/inventory exports; PDF; import/round-trip acceptance fixtures |
| Capacity | Two simultaneous posting tests on PostgreSQL | Representative history sizing; 1,000-user load test; p95 evidence; incremental replay/checkpoints; query profiling |
| Recovery | Transaction rollback tested | Automated encrypted full backups + WAL archive, backup alerts, 15-minute RPO/4-hour RTO restore drills |
| Operations | Versioned migrations, basic request IDs and timings; safe API errors | CI/CD, separate environments, health/metrics/alerts, queue monitoring, uptime and maintenance handling |
| Retention | No application deletion of posted data/history | Accounting/audit/backup retention choices and storage/cost plan |

## Next implementation order

1. Opening account/item balances with a balanced opening equity entry and historical reconciliation fixtures; confirm rounding/precision/return costing defaults with the owner.
2. Harden the web workflow: shared login throttling, account recovery, master pagination, richer book filters, remaining exports, multi-tab draft conflicts and rejected-action auditing.
3. Replace full-history materialization with tested affected-suffix calculations/checkpoints; size representative workloads, then run the full 1,000-user test.
4. Establish deployment environments, runtime database permissions, encrypted backups/WAL archiving, restore drill, observability and release security checks.
5. Build installable desktop and native mobile clients against the shared service, then cross-device retry and reconciliation tests.

No public deployment, production database, backup retention policy, native-app release, or compliance claim was created in this milestone.
