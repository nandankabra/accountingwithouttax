# Backup, recovery and account security

## Encrypted full backups

The backup tool streams a PostgreSQL custom-format dump into AES-256-GCM encryption with a fresh random 96-bit nonce, authenticated header and 128-bit tag. It never writes the unencrypted dump during backup creation. A 32 GiB per-file cap keeps the operation bounded. Key and output files use owner-only filesystem permissions.

```sh
.venv/bin/python scripts/backup.py init-key .runtime/backup-key
.venv/bin/python scripts/backup.py --key-file .runtime/backup-key create
.venv/bin/python scripts/backup.py --key-file .runtime/backup-key verify .runtime/backups/FILE.sbk
.venv/bin/python scripts/backup.py --key-file .runtime/backup-key restore .runtime/backups/FILE.sbk --database simplebooks_recovery_check
```

Replace `FILE.sbk` with the filename returned by creation. Key creation refuses to replace an existing key. Keep a protected, independently recoverable copy of production keys outside the application host; encrypted backups are unusable without the matching key. The local example key is development-only and Git-ignored. Never put key contents in source, CLI arguments, logs or a backup alongside its ciphertext.

Verification authenticates the entire archive before running `pg_restore --list`. Restore authenticates into a private temporary directory, then creates a **new** destination database and restores in one transaction. It rejects the source database, PostgreSQL system names and any existing destination. It does not contain a `DROP DATABASE` or `--clean` path. Temporary plaintext is removed when verification/restore finishes or fails.

Use the standard `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`/`.pgpass` variables. Production connections should use `PGSSLMODE=verify-full` and the appropriate root certificate. Defaults connect only to this project's isolated development cluster. The PostgreSQL client version must support the server/archive version.

Creation emits metadata including conservative snapshot-start time, completion time, duration, bytes, SHA-256, and a non-secret key fingerprint. A failed operation exits nonzero with a sanitized JSON error. No retention deletion is implemented while the owner's retention decision is pending.

## Scheduling and alerts

`ops/systemd/` contains Linux operator templates for a daily full backup at approximately **02:00 Asia/Kolkata**, with a critical journal alert on service failure. They are not installed or enabled on this Mac. To use them on the deployment host, create the dedicated `simplebooks-backup` OS user, install source under `/srv/simplebooks`, create its private backup directory, configure `/etc/simplebooks/backup.env`, adjust paths, then install/enable the timer through the operator's normal deployment process.

Example environment keys (values supplied outside source):

```text
PGHOST=database.internal
PGPORT=5432
PGDATABASE=simplebooks
PGUSER=simplebooks_backup
PGSSLMODE=verify-full
BACKUP_KEY_FILE=/etc/simplebooks/backup-key
BACKUP_DIRECTORY=/var/backups/simplebooks
```

The operator must route critical journal entries and missing-success/late-backup checks into their alert system. An on-host encrypted dump alone is not disaster recovery: off-host storage, independent keys, permissions, backup freshness checks and periodic drills are required.

**This tool is a logical full backup, not WAL archiving/PITR.** The report's 15-minute RPO still needs continuous archived WAL or a managed PostgreSQL PITR service, validated against the deployed workload. Configure physical base backups and WAL retention with the database operator; do not claim that the daily timer meets the RPO.

## Local restore evidence

A synthetic workspace was backed up, authenticated and restored into a separate database on 7 October 2026. It contained 12 vouchers, 14 revisions and 19 audit events at that time. Row-count and complete-row fingerprints matched for workspace, account, item, voucher, revision, journal, stock movement and audit tables. The small fixture restored in approximately 0.15 seconds. This proves the local path works, not a production RTO on representative data.

The retained machine-readable evidence is `.runtime/restore-evidence.json`; the restored test database is named in that file. It is isolated from `simplebooks` and is not used by the running app.

## Account security

`/security/` changes the signed-in owner's password after validating the current password and new-password policy. The current session stays valid; other sessions fail their password-hash check. Security events are append-only audit records.

Password-reset requests use the workspace email, a single-use Django token expiring in 15 minutes, and a canonical origin from `APP_PUBLIC_URL`. Reset replies do not disclose whether an account exists. Per-account and per-IP limits are stored in PostgreSQL under row locks, so limits apply across application workers. Login limits also use shared counters. Anonymous attempts are recorded without falsely identifying them as authenticated owner actions.

Development reset emails are written only to the private `.runtime/mail` directory; no external email is sent. Production requires SMTP configuration:

```text
APP_PUBLIC_URL=https://books.your-domain.example
EMAIL_HOST=your.smtp.provider
EMAIL_PORT=587
EMAIL_HOST_USER=provided-outside-source
EMAIL_HOST_PASSWORD=provided-outside-source
DEFAULT_FROM_EMAIL=Simple Books <no-reply@your-verified-domain.example>
```

Run `manage.py check --deploy` with production environment values. Checks reject a non-HTTPS reset origin, missing SMTP configuration and the placeholder sender. Reset tokens are redacted from Django development-server access logs. Configure the reverse proxy/load balancer to redact these URL segments as well.

Per-IP limits currently use the connection's `REMOTE_ADDR`, not untrusted forwarding headers. Behind a proxy, ensure client addresses are supplied by trusted infrastructure and review `LOGIN_IP_LIMIT` for shared IPs. Periodically remove expired `AuthThrottle` rows and run Django's `clearsessions`; no financial/audit data should be purged through that maintenance path.

Production email delivery, operator alert delivery, off-host recovery, WAL/PITR and retention enforcement are not claimed as tested by the local evidence.
