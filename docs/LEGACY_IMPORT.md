# Legacy import

The optional importer is conservative and currently covers workspaces, users, brands/platforms/products/projects/campaigns/tags, requests, deliverables, creatives, versions, comments, feedback and relationships. It does **not** claim full migration of all legacy tables.

```powershell
cd backend
.venv\Scripts\python.exe manage.py import_legacy_creativemanager --database C:\exports\legacy.sqlite --dry-run --report migration-report.json
.venv\Scripts\python.exe manage.py import_legacy_creativemanager --database C:\exports\legacy.sqlite --report migration-report.json
```

The source opens read-only and is hashed before/after. Dry run executes validation within a rolled-back target transaction. Reports include counts, imported/existing mappings, orphan/duplicate errors and unsupported populated tables. The default real import rolls back if there are unresolved findings. `--allow-partial` is an explicit operator override only after reviewing the report and retaining the original source backup.

Mapping identity is `(source SHA-256, table, legacy ID)`; rerunning the same immutable source resumes without duplicate target identities. A changed export is a different source and needs an explicit migration plan. Import is one atomic batch in this release, so large datasets should be staged and tested before use.

Legacy `in_review` maps to version `submitted` or request `ready_for_review`. User passwords and integration tokens are not migrated. Imported users are inactive with unusable passwords until an administrator verifies identity, resets credentials and configures memberships/brand restrictions. Existing email conflicts are reported, never silently merged.

No source company SQLite database was supplied, only PHP code/migrations. The importer was tested with generated SQLite fixtures, not your actual legacy data. A real migration report can be produced only from your exported database. Preserve the immutable ZIP and database export until every historical entity and relationship has been reconciled.
