# Accounts, activation keys and subscription control

The current local administration panel is **http://127.0.0.1:8017/admin/**. Sign out of a customer account before signing in as the provider. The existing local provider login is `operator@example.test` with password `Local-operator-demo-7429`. This is a local review credential, not a production credential, and is excluded from client installers. A deployed server needs a provider account with your own password.

Create a provider on the server:

```sh
python manage.py create_operator --email your-provider@example.com
```

The command prompts for a strong password and refuses to promote an existing customer. Do not put the password in command-line arguments. Product administration is available only to active superusers.

## Create and activate a customer

1. Open **Customer companies → Add**. Enter the company name/contact details, customer login email and matching initial password. Save. The new account has empty books and is suspended until you activate its subscription.
2. Create the required **Subscription plan**, including its INR price and duration. Payments are collected separately from this application.
3. Open **Subscriptions** and select the customer. Choose the plan, set **Status = Active**, and set **Starts on** and **Expires on**. Dates are inclusive in the server's Asia/Kolkata timezone. Save.
4. Click **Generate / replace subscription key**, then **Generate subscription key**. Copy the key from that one-time response and give it privately to this customer.
5. The customer installs the appropriate DMG/EXE, pastes the key and clicks **Activate & open books**. The key signs into that customer's company account. Treat it like a password; anyone holding it can access the account. Password login and recovery are also available.

The key contains the configured server address, so customers do not need to type a URL. Set **APP_PUBLIC_URL to the actual public HTTPS origin before issuing client keys**. The current local default, `http://127.0.0.1:8017`, works only when the application and backend run on the same computer. It cannot connect a client's PC to this Mac. Moving the server to another origin requires new keys.

Only key digests are stored in the subscription table. Existing key plaintext cannot be retrieved; generate a replacement if a customer loses it. Issuing a replacement invalidates the old key and all sessions activated with it. Keys cannot grant provider administration.

## Renew, expire or revoke

- **Renew:** set Status to Active and extend Expires on. The existing key continues to work. The customer can reload the app; no reinstall is required.
- **Expiry:** after the expiry date, new accounting/master writes and fresh key activations are blocked by the server. Existing authenticated customers may read/export their retained books.
- **Suspend:** set Status to Suspended and save to block financial writes immediately.
- **Revoke key access:** clear Key enabled and save. Activated sessions are revoked on their next request. Re-enable only when intended or issue a replacement.
- **Disable all account sign-in:** in Users, clear the customer's Active flag. Records are preserved.

Public signup is disabled by default. Customers receive no provider privileges. Company/subscription changes, key issuance and activation create audit records; raw keys are not put in audit data, application logs or URLs.

The same key can activate multiple computers for the same company. Device-count limits and offline licensing are not implemented. An internet connection and an available accounting server are required.

## Distribution status

Version 0.3.0 packages contain only the connected desktop application, icon and required Electron notices. No database, customer accounts, sample records, administrator credentials or subscription keys are embedded. Apple Silicon and Intel DMGs and Windows x64 EXE are built locally. Mac package activation is verified locally; Windows execution remains unverified. Packages are not signed with a trusted publisher certificate or notarized, so customer distribution still requires signing and platform acceptance.
