# Delivery acceptance checklist

Current result: **demo features implemented; client production delivery remains pending.** Automated passing tests do not mean every platform, deployment or recovery requirement is accepted.

| Check | Evidence/status |
|---|---|
| Accounting, inventory, isolation, rollback, retries and concurrency regressions | 66 Django/PostgreSQL tests pass locally |
| PDF for all eight voucher types, private access, company data and escaped text | Automated tests pass; all eight synthetic layouts reviewed |
| Long PDF pagination, repeated headers and rupee glyph | 100-line tests pass; seven-page synthetic layout reviewed |
| Editable company contacts and concurrent update protection | Tests pass; browser form reviewed |
| Provider access, strong customer passwords, customer provisioning | Tests pass; provider screens reviewed |
| Subscription suspension, expiry, renewal, read/export access | Tests pass; provider dates/status screen reviewed |
| Revision-history section removed | Current detail API and browser screen checked; database protections retained |
| Windows installer packaging, x64 app, metadata, bundled source and digest | Built on Mac; release manifest records package contents |
| Desktop server setup and sign-in | macOS development wrapper reviewed |
| Encrypted local backup/restore after dependency update | All 23 tables match full-row fingerprints, including customer/subscription data; small fixture only |
| Python runtime dependency audit | No known vulnerabilities after cryptography upgrade |
| Desktop runtime npm dependency audit | No findings; app has no runtime npm dependency tree |
| Complete desktop build-tool dependency audit | **Open:** one unpatched `sprintf-js` advisory affects eight development dependency entries; excluded from shipped app, build pipeline still needs review |
| Windows install/launch/update/uninstall as non-admin | **Pending on Windows x64 PC** |
| Windows server setup, valid HTTPS, sign-in/out, company save, all voucher flows, PDF save/open, CSV download | **Pending on Windows x64 PC** |
| Windows WhatsApp handoff and actual authorised message/PDF receipt | **Pending with an agreed test recipient** |
| Signed executable and publisher/SmartScreen acceptance | **Pending code-signing certificate and Windows acceptance** |
| Hosted server/domain/TLS, real password-recovery mail and health checks | **Pending deployment** |
| Production data volumes and sustained capacity targets | **Pending:** earlier 1,000-user synthetic runs missed latency targets |
| Off-host backups, continuous WAL/PITR, delivered alerts, production RPO/RTO restore drill | **Pending deployment and exercises** |
| Latest-two browser versions, physical devices, accessibility and accounting-owner acceptance | **Pending agreed acceptance matrix** |

For Windows acceptance use a separate demo customer with synthetic records. Record Windows edition/build, installer SHA-256, server release/origin, browser/WhatsApp versions, observed totals, download names, screenshots and each outcome. Retest changed or failed scenarios; preserve any user-entered business data.

Automatic subscription billing and offline accounting are outside the implemented baseline. Prices, expiry dates and renewals are managed by the provider; the executable uses the shared accounting service. If either alternative is selected, its implementation and acceptance tests become additional release gates.
