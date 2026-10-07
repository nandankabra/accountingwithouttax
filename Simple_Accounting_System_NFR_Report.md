# Simple Accounting System — Non-Functional Requirements (NFR)

**Version:** 1.1  
**Date:** 6 October 2026  
**Status:** Updated with owner decisions; remaining defaults require review

## 1. Purpose

This document defines the non-functional requirements for a simple accounting/bookkeeping system that works on MacBook, Windows, and mobile devices and supports approximately 1,000 simultaneous users.

The system is intended for straightforward “kacha”/basic accounting. It must remain simple, fast, reliable, and easy for non-technical users.

## 2. In-scope modules

1. Dashboard
2. Accounting vouchers:
   - Payment
   - Receipt
   - Sales
   - Purchase
   - Credit note with item-wise details
   - Debit note with item-wise details
3. Accounting books:
   - Ledger
   - Inventory book

## 3. Explicitly out of scope for this phase

- GST, VAT, TDS, tax calculation, tax returns, and tax reports
- Payroll and attendance
- Banking integration and bank reconciliation
- E-invoicing/e-way bill
- Manufacturing, production, and advanced costing beyond basic inventory valuation
- CRM, procurement workflow, and project management
- Automatic government compliance filing

## 4. Quality priorities

The priorities are: data correctness, ease of use, security, availability, responsive performance, auditability, and maintainability.

## 5. Platform and compatibility requirements

| ID | Requirement | Acceptance evidence |
|---|---|---|
| PLAT-01 | Installable desktop applications shall work on supported macOS and Windows versions, alongside the responsive web application. | Cross-platform acceptance test on supported MacBook and Windows devices. |
| PLAT-02 | The application shall support both responsive mobile browsers and installable native Android and iOS applications. | Mobile test matrix covering login, dashboard, voucher entry, search, and ledger viewing. |
| PLAT-03 | The responsive interface shall support desktop, tablet, and mobile screen sizes without horizontal scrolling for normal workflows. | Responsive UI test at defined breakpoints. |
| PLAT-04 | Browser-based functions shall support the latest two major versions of Chrome, Edge, Safari, and Firefox where applicable. | Compatibility test report. |
| PLAT-06 | All clients shall share the same authoritative accounting data and posting rules. Failed or retried synchronization shall not duplicate vouchers. Full offline posting is not yet specified. | Cross-device reconciliation and retry tests. |
| PLAT-05 | User entries shall be preserved when a temporary network interruption occurs before final submission. | Offline/interruption recovery test. |

## 6. Usability requirements

| ID | Requirement | Acceptance evidence |
|---|---|---|
| USE-01 | A trained first-time user shall be able to create a valid payment or receipt voucher without assistance. | Usability test with representative users. |
| USE-02 | Voucher screens shall use consistent labels, keyboard navigation, date fields, party/account selection, item selection, quantity, rate, amount, narration, and save actions. | UI review against approved screen designs. |
| USE-03 | The system shall display clear validation messages beside the relevant field. | Validation test for missing, invalid, and inconsistent values. |
| USE-04 | Destructive actions such as delete, cancel, or reverse shall require confirmation and explain the consequence. | UX acceptance test. |
| USE-05 | Common accounting operations shall be reachable within three navigation levels from the dashboard. | Navigation review. |
| USE-06 | The interface shall support readable text, adequate contrast, visible focus states, and accessible form controls. | Accessibility review targeting WCAG 2.1 AA principles. |
| USE-07 | The system shall provide search, filter, sort, pagination, and date-range controls for books and voucher lists. | Functional usability test. |

## 7. Functional integrity requirements

| ID | Requirement | Acceptance evidence |
|---|---|---|
| INT-01 | Every saved voucher shall have a unique, non-reusable identifier. | Automated uniqueness test. |
| INT-02 | A voucher shall not be saved unless all mandatory fields are valid. | Automated validation tests. |
| INT-03 | Debit and credit effects shall balance according to the approved accounting model before posting. | Posting and balancing test suite. |
| INT-04 | Posted transactions shall be reflected consistently in the dashboard, ledger, and inventory book. | Cross-module reconciliation test. |
| INT-05 | Item-wise credit and debit notes shall retain item, quantity, rate, amount, and reference-voucher details where applicable. | Item-note test cases. |
| INT-06 | Inventory book changes shall be traceable to the relevant sales, purchase, credit-note, or debit-note transaction. | Inventory traceability test. |
| INT-07 | Duplicate submission caused by double-clicking or retrying shall not create duplicate vouchers. | Idempotency test. |
| INT-08 | The system shall prevent unauthorized editing or deletion of posted records. | Permission and posting-state tests. |
| INT-09 | Any correction to a posted record shall use an approved edit, reversal, or adjustment workflow and retain the original record. | Audit and reversal test. |
| INT-10 | Totals shall be calculated on the server and validated against client-side totals before posting. | Tamper and calculation tests. |

## 8. Performance and scalability requirements

The target capacity is approximately 1,000 concurrent active users. Capacity planning shall be validated with realistic voucher-entry, search, dashboard, and ledger workloads.

| ID | Requirement | Target |
|---|---|---|
| PERF-01 | The system shall support 1,000 concurrent authenticated users without data corruption or service instability. | Load test at 1,000 concurrent users. |
| PERF-02 | At least 95% of normal API requests shall complete within 2 seconds under agreed baseline load. | Performance test report. |
| PERF-03 | Voucher save/post operations shall complete within 3 seconds for 95% of requests under baseline load. | Transaction performance test. |
| PERF-04 | Standard dashboard and ledger queries shall return within 3 seconds for 95% of requests on the agreed data volume. | Query performance test. |
| PERF-05 | Large book results shall use pagination or controlled export; the system shall not load an unbounded result set into the client. | Pagination and memory test. |
| PERF-06 | The architecture shall allow horizontal scaling of application services without changing accounting data semantics. | Architecture review and scale-out test. |
| PERF-07 | Slow queries, failed requests, queue depth, CPU, memory, database connections, and response time shall be observable. | Monitoring dashboard and alert test. |

## 9. Availability, reliability, and recovery

| ID | Requirement | Target |
|---|---|---|
| REL-01 | Monthly production availability shall be at least 99.5%, excluding approved maintenance. | Monthly availability report. |
| REL-02 | A failed request shall return a safe, understandable error and shall not partially post an accounting transaction. | Failure-injection test. |
| REL-03 | Voucher posting shall be atomic: either all related accounting and inventory entries are committed, or none are committed. | Transaction rollback test. |
| REL-04 | Automatic backups shall include at least daily full backups plus incremental or transaction-log recovery points sufficient to meet the 15-minute RPO. Backup failures shall alert the operator. | Backup logs. |
| REL-05 | Recovery Point Objective (RPO) shall be no more than 15 minutes for production data. | Disaster-recovery test. |
| REL-06 | Recovery Time Objective (RTO) shall be no more than 4 hours for a major service outage. | Recovery exercise report. |
| REL-07 | Backups shall be encrypted, access-controlled, and periodically tested by restoring them. | Restore-test evidence. |
| REL-08 | Planned maintenance shall display a notice and shall not silently lose unsaved user input. | Maintenance-window test. |

## 10. Security and access control

| ID | Requirement | Acceptance evidence |
|---|---|---|
| SEC-01 | All authenticated traffic shall use HTTPS/TLS. | Configuration and security scan. |
| SEC-02 | Passwords shall never be stored in plain text and shall use a modern adaptive password hash. | Security review. |
| SEC-03 | Sessions shall expire after a configurable period of inactivity and support secure logout. | Session-security test. |
| SEC-04 | Each accounting workspace shall have exactly one owner/admin account. No additional staff roles or approval hierarchy are required. | Single-admin authorization tests. |
| SEC-05 | Server-side authorization shall validate authenticated ownership of the requested accounting workspace for every protected operation. | Authorization and tenant-isolation tests. |
| SEC-06 | Users shall not be able to access records by changing an identifier in a URL or API request. | Insecure direct object reference test. |
| SEC-07 | Sensitive configuration and secrets shall be stored outside source code and rotated through controlled configuration. | Deployment inspection. |
| SEC-08 | Inputs shall be validated and protected against SQL injection, XSS, CSRF, command injection, and unsafe file handling. | Automated and manual security testing. |
| SEC-09 | Administrative actions, login events, account-security changes, posting, reversal, and export shall be logged. | Audit-log review. |
| SEC-10 | The product shall follow secure development and dependency-update practices, including vulnerability scanning before release. | Release security checklist. |

## 11. Auditability and accounting traceability

| ID | Requirement | Acceptance evidence |
|---|---|---|
| AUD-01 | Each created, edited, posted, reversed, cancelled, or deleted-attempted record shall retain user, timestamp, action, and reason where required. | Audit-log test. |
| AUD-02 | Posted vouchers shall retain their original values and revision history. | Revision-history test. |
| AUD-03 | Audit logs shall be append-only and protected from alteration or deletion through admin-facing application operations. | Tamper-resistance test. |
| AUD-04 | Ledger entries shall link back to their source voucher. | Drill-down test. |
| AUD-05 | Reports and exports shall show generation time, selected period, organisation, and generating user. | Export review. |
| AUD-06 | Time handling shall be consistent and shall record the configured organisation timezone. | Timezone test. |

## 12. Data management and correctness

| ID | Requirement | Acceptance evidence |
|---|---|---|
| DATA-01 | Monetary values shall use fixed-precision decimal arithmetic and INR amounts shall be displayed and posted to two decimal places, representing rupees and paise. One deterministic rounding rule shall apply across all clients and the server; higher internal precision may be used for valuation calculations. | Code and calculation review. |
| DATA-02 | Date, number, quantity, rate, and amount formats shall be consistent throughout the system. | Data-format test. |
| DATA-03 | Required master data used by vouchers, such as accounts, parties, and items, shall be validated before use. | Master-data validation test. |
| DATA-04 | Database constraints shall protect required relationships, unique identifiers, valid statuses, and non-negative quantities where applicable. | Schema and integrity tests. |
| DATA-05 | Data deletion shall be restricted; financial records shall normally be archived, cancelled, or reversed rather than physically deleted. | Deletion-policy test. |
| DATA-06 | Export is required. CSV and PDF are proposed initial formats pending owner selection; exports are not a substitute for recoverable backups. | Export acceptance test. |
| DATA-07 | Imported or exported data shall preserve identifiers, dates, quantities, rates, totals, and status without silent truncation. | Round-trip data test. |

## 13. Dashboard requirements

| ID | Requirement | Acceptance evidence |
|---|---|---|
| DASH-01 | The dashboard shall show only the signed-in admin’s accounting workspace. | Workspace ownership test. |
| DASH-02 | The dashboard shall provide current-period summaries for receipts, payments, sales, purchases, credit notes, debit notes, and outstanding balances where supported by the approved accounting model. | Dashboard reconciliation test. |
| DASH-03 | Dashboard figures shall be drillable to the underlying vouchers or books. | Drill-down test. |
| DASH-04 | Dashboard data shall clearly show the selected date range and last refresh status. | UI review. |
| DASH-05 | Dashboard widgets shall degrade safely if a non-critical widget fails; core navigation and voucher operations shall remain usable. | Resilience test. |

## 14. Maintainability and supportability

| ID | Requirement | Acceptance evidence |
|---|---|---|
| MAINT-01 | The system shall have separate development, testing, staging, and production environments. | Deployment review. |
| MAINT-02 | Source code shall use version control, code review, automated tests, and documented release versions. | Repository and release checklist. |
| MAINT-03 | Critical accounting logic shall have automated unit and integration tests. | Test coverage report and test cases. |
| MAINT-04 | Database schema changes shall be versioned and reversible where practical. | Migration review. |
| MAINT-05 | Application logs shall be structured, searchable, timestamped, and free of passwords or sensitive secrets. | Logging review. |
| MAINT-06 | Operators shall receive alerts for service failure, high error rate, backup failure, storage exhaustion, and abnormal latency. | Alert simulation. |
| MAINT-07 | User-facing errors shall include a support/reference ID without exposing internal stack traces. | Error-handling test. |
| MAINT-08 | API and deployment documentation shall be maintained for future development and support. | Documentation review. |

## 15. Release gates

The first production release shall not be approved until all of the following are demonstrated:

- Voucher posting, reversal, ledger generation, and inventory-book updates reconcile correctly.
- Single-admin authorization and isolation between independent accounting workspaces pass.
- No critical or high-severity security defects remain open.
- 1,000-concurrent-user load testing passes the performance targets. A staged deployment below this capacity must be labelled as such and cannot claim compliance with this target.
- Backup restoration and disaster-recovery tests pass.
- Cross-platform tests pass on agreed MacBook, Windows, Android, and iOS configurations.
- Audit history can trace every posted financial record to its source voucher.
- Product owners approve the final accounting rules, master data, numbering, rounding, and correction workflow.

## 16. Confirmed owner decisions and remaining design defaults

| Topic | Confirmed requirement |
|---|---|
| Delivery | Responsive web app, installable macOS and Windows desktop apps, and native Android/iOS apps; mobile browsers also supported. |
| Accounting | Familiar basic double-entry bookkeeping and voucher workflow, described by the owner as similar to Tally Prime. This is a workflow reference, not a requirement to reproduce its full feature set. |
| Business scope | One business per accounting workspace; no multiple companies, branches, or staff accounts within that workspace. |
| Access | One admin account per workspace; no operator, viewer, auditor roles or approval hierarchy. Audit history remains an internal system capability. |
| Inventory | Both quantity tracking and stock valuation/costing. |
| Currency | INR, rupees and paise, with two decimal places for posted amounts and display. This does not specify voucher numbering. |
| Corrections | Both editing posted vouchers and reversal/adjustment are required, with complete history and consistent recalculation. |
| Export and backup | Export required; automatic backups required. Formats and retention duration are not yet specified. |
| Capacity | Approximately 1,000 simultaneous users. Assumed to mean 1,000 independent admin workspaces across the service, rather than 1,000 staff accounts in one business. This interpretation needs confirmation. |

### 16.1 Proposed accounting baseline

These are proposed functional rules to make the NFR integrity tests concrete; they are not a verified specification of another product.

| Voucher | Proposed financial posting | Inventory effect |
|---|---|---|
| Payment | Debit selected party/expense account; credit cash/bank ledger. | None. |
| Receipt | Debit cash/bank ledger; credit selected party/income account. | None. |
| Sales | Debit customer or cash/bank; credit sales account. | Reduce sold quantities; apply the approved stock valuation policy. |
| Purchase | Debit purchase or inventory account under the selected accounting policy; credit supplier or cash/bank. | Increase purchased quantities and associated cost. |
| Item-wise credit note (sales return) | Debit sales-return account; credit customer or cash/bank. | Restore returned quantities with traceable cost. |
| Item-wise debit note (purchase return) | Debit supplier or cash/bank; credit purchase-return or inventory account under the selected policy. | Reduce returned quantities and associated cost. |

Cash/bank here means bookkeeping ledgers only, not banking integration. Opening balances for accounts and items are necessary supporting data. Selection of periodic versus perpetual inventory accounting must be settled before posting rules are implemented, so purchases and cost of goods sold are not double-counted. Value-only item adjustments must not create physical stock movement.

### 16.2 Additional acceptance requirements from these decisions

| ID | Requirement | Acceptance evidence |
|---|---|---|
| INV-01 | Inventory book shall show opening quantity/value, inward and outward movements, closing quantity/value, and source voucher. | Quantity and value reconciliation fixtures. |
| INV-02 | One approved valuation method shall be applied consistently. Moving weighted average is a proposed default; FIFO remains an alternative requiring selection. | Known-cost purchase, sale, and return fixtures. |
| INV-03 | Backdated postings, edits, and reversals shall recalculate affected subsequent quantities and values deterministically, retaining calculation history. | Backdated correction and return tests. |
| INV-04 | Negative-stock handling shall be explicit. Blocking transactions that would make stock negative is the proposed default. | Simultaneous sale and insufficient-stock tests. |
| EDIT-01 | Posted edits shall retain before/after values, admin identity, time, and reason; replace the prior financial/stock effects atomically rather than adding duplicate effects. | Posted-edit reconciliation and rollback tests. |
| EDIT-02 | Concurrent edits from different devices shall detect stale versions and require refresh/review rather than silently overwriting newer changes. | Two-device conflict test. |
| EDIT-03 | Reversal shall create a linked compensating record and preserve the original. Repeated reversal requests shall not duplicate accounting or stock effects. | Reversal and retry tests. |
| SYNC-01 | Web, desktop, and mobile shall show consistent balances after successful posting; clients shall distinguish unsaved drafts from committed vouchers. | Cross-client posting and connectivity tests. |

### 16.3 Remaining unspecified details

- **Voucher numbering:** Proposed separate sequential series per type, for example PAY-000001, REC-000001, SAL-000001, PUR-000001, CN-000001, and DN-000001. Annual reset/manual entry policy remains unspecified. Internal IDs remain globally unique even if display series reset.
- **Rounding:** Proposed decimal half-up rounding to the nearest paise, with a documented line-total versus document-total policy before implementation.
- **Inventory policy:** Confirm valuation method, periodic/perpetual accounting, item units/quantity precision, return costing, and negative-stock policy.
- **Export formats:** CSV and PDF proposed; Excel has not been confirmed.
- **Retention:** Accounting/audit retention and backup retention remain unspecified. Proposed operational backup retention is 30 days plus 12 monthly snapshots; these are design defaults, not confirmed or statutory durations.
- **Capacity interpretation:** Confirm 1,000 independent single-admin users across the service. Vouchers, items, history size, request frequency, and workload mix still need sizing; 1,000 users does not specify these volumes.
- **Connectivity:** Temporary draft protection is required. Full offline bookkeeping and later reconciliation are not yet requested.

The above defaults allow design planning to continue, but shall not be presented as owner-approved choices.

## 17. Acceptance statement

The system is NFR-compliant for this phase only when the stated targets are tested, the evidence is recorded, and the product owner approves the unresolved decisions in Section 16. Functional requirements may be expanded later, but new modules must not weaken the security, performance, audit, backup, and accounting-integrity requirements in this document.
