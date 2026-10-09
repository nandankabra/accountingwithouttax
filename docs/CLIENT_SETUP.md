# Install Simple Books Local 0.4.0 on Windows

1. Run `SimpleBooks-Local-Setup-0.4.0-x64.exe` on Windows 10/11 x64 and choose the installation directory. Python/PostgreSQL are not required separately.
2. Launch Simple Books from the desktop shortcut. Copy the **Installation ID** and send it privately to your provider.
3. Paste the provider's **offline Windows key** (begins `SB2.`) and choose **Activate & open books**. The previous connected-server `SB1.` keys do not work with this edition.
4. Your company starts empty. Add accounts/items, opening balances and vouchers. Edit name/mobile/address under **Company details**.
5. Use the PDF and WhatsApp buttons on voucher details. PDFs work offline; WhatsApp needs internet and may require manually attaching the downloaded PDF.

Your books remain on this PC. You can close the provider's admin server and disconnect the network after receiving a key. No Mac/server needs to stay running. This edition supports one company/owner per Windows profile and is not a multi-PC shared database.

Renewal: ask the provider to issue a new key for the same Installation ID with the new expiry. Choose **Simple Books → Enter / renew subscription key** and paste it. Existing books and company edits remain. **Open saved books** returns to retained books without replacing a key. Expiry blocks posting, edits and master creation, while reading/PDF/CSV export remain available.

**Backups:** choose **Simple Books → Back up company…** and save the `.sqlite3` file to another drive. Save a copy of `installation.json` from **Open local data folder** too. **Restore company backup…** checks the file and saves a copy of the current database before replacement. Restoring on another installation requires a matching renewal/replacement key from the provider. Database backups contain posted records; unposted browser drafts are not included. Do not copy a live database file manually.

Data is under `%APPDATA%\SimpleBooksLocal`. Uninstalling/updating preserves it. The database is not encrypted; Windows account/file permissions protect local access. Startup keeps thirty recent snapshots, which do not replace off-device backups. Set the PC date correctly: a detected backward date change blocks writes/activation. Offline expiry cannot resist an administrator who modifies software, restores older data or changes the machine clock; it does not provide online revocation.

This installer is unsigned. Automated accounting/licensing checks and local desktop tests were performed on Mac; actual Windows installation, runtime and uninstall/upgrade acceptance must be performed before declaring the release fully Windows-tested. See the release acceptance checklist.

Provider administration is separate from the installed customer app; see `docs/ADMINISTRATION.md`.
