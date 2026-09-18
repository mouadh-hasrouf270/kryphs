# Backup and restore

The backup command uses SQLite's online backup API, not a raw copy of a live WAL file. It verifies database integrity and writes a timestamped ZIP with the database, local media and a non-secret manifest. It never embeds `.env` or the encryption key.

```powershell
cd backend
.venv\Scripts\python.exe manage.py backup_database --directory backups --retain 14
.venv\Scripts\python.exe manage.py check_database
```

For a consistent database-plus-media snapshot, pause uploads and external jobs during the backup window. The database snapshot itself is online-safe; local media are copied afterward and are not part of the same transactional snapshot. Keep adequate disk headroom.

Retention removes only timestamped `cm-*.zip` files in the explicitly selected backup directory. Set `--retain 0` to disable retention. Schedule with Windows Task Scheduler or a host cron/systemd timer. Protect backups because they contain company data and encrypted credentials.

Restore into a **new** directory; the command never overwrites an existing deployment:

```powershell
.venv\Scripts\python.exe manage.py restore_database backups\cm-TIMESTAMP.zip --destination recovered
```

The restore checks archive paths and SQLite integrity before copying files. Stop web and worker; set `DATABASE_PATH` to the recovered `database.sqlite3` and `MEDIA_ROOT` to its `media` directory. Restore the original `APP_ENCRYPTION_KEY` from your secure key backup. Restart, run `check_database`, verify counts and memberships, then test provider access.

Drive binaries are external to the backup; Drive IDs, connection metadata and folder mappings are in the database. Losing the encryption key requires reconnecting integrations. A compromised key requires credential revocation and an explicit key rotation/migration process; simply replacing the key makes old ciphertext unreadable.

Windows backup cleanup and restore integrity were exercised during QA. See FINAL_QA_REPORT.md for exact results.
