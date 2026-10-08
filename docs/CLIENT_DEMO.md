# Client demo and Windows package — 8 October 2026

The requested PDF, sharing, company details and provider administration features are implemented locally. The Windows x64 installer was built and its contents/metadata checked on macOS. **Installation and acceptance on Windows remain required. This is a demo candidate, not a signed production release.**

## Start the existing Mac demo

```sh
cd /Users/nandankabra/ondemand/accountingwithouttax
/opt/homebrew/bin/python3 scripts/dev.py
```

Open <http://127.0.0.1:8017/>. The existing sample owner is `demo@example.test`. Its local review password is `Local-review-only-7429`. The provider login is `operator@example.test`, with local demo password `Local-operator-demo-7429`; administration is at <http://127.0.0.1:8017/admin/>. These credentials are for this local demo only. Create separate provider/customer accounts with your own passwords for deployment. Existing demo records are preserved; do not present them as real client books or overwrite them to rehearse a demo.

Create another synthetic demonstration company without modifying the existing company:

```sh
.venv/bin/python manage.py seed_demo --email another-demo@example.test
```

Choose the new demo password at its prompt. The command is limited to development.

## Demonstration sequence

1. Sign in as a company owner. Open **Company details** and show the editable name, mobile, company email, address, city and postal code. Saved changes appear on future voucher PDFs. Concurrent owner edits require a reload instead of silently replacing a newer version.
2. Open a voucher. **Download PDF** is available on payment, receipt, sales, purchase, credit note, debit note, opening and reversal records. PDFs include company details, voucher number/date/status, party, item quantities/rates/amounts, totals and source references. Accounting-cost entries are kept in the books. The PDF uses Indian currency grouping and an embedded licensed rupee-capable font.
3. Click **WhatsApp**. Review/edit the prepared message and optionally enter a country-code phone number. Download the PDF, open WhatsApp, attach the downloaded file and send there. Where the device supports file sharing, **Share PDF…** opens the system share sheet with the PDF. A `wa.me` link cannot attach a private PDF automatically; no public financial-document URL is created. Real message delivery was not performed during testing.
4. Show **Edit voucher**. The revision-history list and version badge are removed from the voucher detail. Corrections still require a reason and retain protected records internally.
5. Sign out, then sign in as the provider. In **Customer companies → Add**, enter company details, customer login email and matching strong password. Saving provisions an isolated owner, standard ledgers and trial subscription. Passwords are hashed.
6. In **Subscription plans**, create your plan names, INR prices and durations. In **Subscriptions**, assign a plan, set trial/active/suspended status and explicit start/expiry dates. To renew, set active and extend the expiry date according to the plan. Prices are metadata; collect payment separately. Automatic checkout, gateway webhooks, recurring debit and payment reconciliation are not implemented.
7. Expired/suspended customers can sign in, read and export their books. New masters and financial writes are rejected. Already committed idempotent retries can still return their original result. Renewing restores posting access.

Provider administration requires an active superuser; a customer's staff flag alone grants no provider access. Financial posting tables are not exposed as editable admin models. Provider company/subscription changes are audited. New self-signup defaults to disabled outside development; `ALLOW_SELF_SIGNUP=0` disables it in development too.

For a new deployment, provision the provider with a password prompt:

```sh
.venv/bin/python manage.py create_operator --email your-provider@example.com
```

The command refuses to promote an existing account. It accepts `OPERATOR_PASSWORD` from the process environment for controlled automation; do not put credentials in command-line arguments or source control.

## Windows demo client

Artifact: `output/desktop/SimpleBooks-Setup-0.2.0-x64.exe` (approximately 106 MB). SHA-256 and the packaged file inventory are in `output/desktop/release-manifest.json`.

Copy the installer to a Windows x64 demonstration PC and install it as a normal user. Launch **Simple Books**, enter your accounting server origin and connect. The client accepts HTTPS; HTTP is allowed only for a server on that same PC, such as `http://127.0.0.1:8017`. `127.0.0.1` on Windows does not refer to this Mac.

**The executable connects to a shared server. It does not bundle PostgreSQL or run accounting offline.** No public server has been deployed by this task. A demonstration on a separate Windows PC needs a reachable trusted HTTPS server, or a separately configured local Windows backend. The development wrapper was connected, signed in and visually reviewed on this Mac; that does not establish Windows compatibility.

The installer is unsigned. Windows publisher/SmartScreen acceptance and organisational distribution policy must be checked on the target PC. Obtain a code-signing certificate and enable signing for customer release. Do not ask customers to disable operating-system or certificate protections.

Rebuild from source with Node.js 22.12+:

```sh
cd desktop
npm ci
npm test
npm run build:win
```

Run the desktop development preview with `npm start` after starting the backend. Server settings are stored separately from credentials in the operating system's SimpleBooks application-data directory. Browser sessions/drafts remain scoped to the selected origin. The app disables Node access in remote pages, isolates/sandboxes the renderer, rejects cross-origin navigation/redirects, and allows only HTTPS WhatsApp links to open externally.

## Verification and release gates

```sh
cd /Users/nandankabra/ondemand/accountingwithouttax
.venv/bin/python scripts/verify.py
.venv/bin/python scripts/preview_vouchers.py
```

Verification uses a separate PostgreSQL test database. The preview generator uses synthetic in-memory data and makes no database queries or writes. `requirements-dev.txt` includes PDF parsing/rendering tools; those tools are excluded from the server runtime requirements. The Noto Sans font licence is in `books/fonts/OFL.txt`. Electron/Chromium notices remain in the Windows distribution.

See [verification evidence](VERIFICATION.md) and the [delivery checklist](RELEASE_CHECKLIST.md). Do not label testing “100% complete” while any release gate remains open.

Sharing references: [WhatsApp click-to-chat](https://faq.whatsapp.com/5913398998672934), [Web Share API](https://developer.mozilla.org/en-US/docs/Web/API/Navigator/share). Desktop reference: [Electron security guidance](https://www.electronjs.org/docs/latest/tutorial/security).
