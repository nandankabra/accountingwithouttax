# Delivery acceptance checklist

Current result: **demo features implemented; client production delivery remains pending.** Automated passing tests do not mean every platform, deployment or recovery requirement is accepted.

| Check | Evidence/status |
|---|---|
| Accounting, inventory, isolation, rollback, retries and concurrency regressions | 77 Django/PostgreSQL tests pass locally |
| PDF for all eight voucher types, private access, company data and escaped text | Automated tests pass; all eight synthetic layouts reviewed |
| Long PDF pagination, repeated headers and rupee glyph | 100-line tests pass; seven-page synthetic layout reviewed |
| Editable company contacts and concurrent update protection | Tests pass; browser form reviewed |
| Provider access, strong customer passwords, customer provisioning | Tests pass; provider screens reviewed |
| Subscription suspension, expiry, renewal, read/export access | Tests pass; provider dates/status screen reviewed |
| Revision-history section removed | Current detail API and browser screen checked; database protections retained |
| Windows EXE/Mac DMGs packaging, x64 app, metadata, bundled source and digest | Built on Mac; release manifest records package contents |
| Desktop server setup and sign-in | Apple Silicon packaged app launched and activated against isolated QA server; both DMG checksums verified |
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

Version 0.3.0 removes client badges and adds provider-issued subscription-key activation. New customers remain suspended until the provider activates dates and issues a key. Key expiry/renewal/revocation are tested. The shared public HTTPS server/domain is still missing, so activation from a separate client computer is not yet ready.

## Standalone Windows 0.4.0 acceptance — still requires a Windows PC

- [ ] Install the 0.4.0 local EXE on a clean Windows 10/11 x64 profile without Python/PostgreSQL; launch from shortcut.
- [ ] Obtain an SB2 key for its installation ID, disconnect the network, activate, and verify an empty company.
- [ ] Create accounts/items/opening stock; post all voucher types, correct a voucher, and verify ledger/stock totals and negative-stock blocking.
- [ ] Update company details; download PDFs and CSVs. With internet restored, open WhatsApp and attach a PDF.
- [ ] Close/reopen the app and verify persisted data; open a second instance and confirm only one local engine/window.
- [ ] Save/overwrite a backup, post another voucher, restore the earlier backup, and verify the automatic before-restore copy.
- [ ] Test a short licence at expiry: reads/PDFs remain, writes fail; paste a renewal key for the same ID and verify no data loss.
- [ ] Reject an altered key, wrong-installation key, old renewal, damaged backup and ordinary browser/network access to the local service.
- [ ] Uninstall/reinstall or upgrade and verify preserved profile data/installation ID. Close the app and verify the local service terminates.
- [ ] Verify publisher signing/trusted distribution before client rollout. No Windows runtime/signing acceptance was claimed by the Mac build.
