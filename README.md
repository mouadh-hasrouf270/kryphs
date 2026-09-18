# CreativeManager

A standalone Django + React creative operations application, built from the supplied CreativeManager specification and legacy PHP reference. No PHP Core Platform is required.

**Status:** runnable and tested local implementation. The entire master specification is **not yet production-accepted**. Read [known limitations](docs/KNOWN_LIMITATIONS.md), [requirement traceability](docs/REQUIREMENTS_TRACEABILITY.md), and the [QA report](docs/FINAL_QA_REPORT.md) before a company rollout.

## Start on this Windows machine

From the `creative-manager` directory, open three terminals:

```powershell
# Terminal 1 — API
cd backend
.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8017
```

```powershell
# Terminal 2 — interface
cd frontend
npm.cmd run dev
```

```powershell
# Terminal 3 — background operations
cd backend
.venv\Scripts\python.exe manage.py run_worker
```

Open **http://127.0.0.1:5173**. The API deliberately uses **8017**, because port 8000 was already occupied on the development machine. The Vite proxy is configured accordingly.

Local demo login: **manager@demo.local** / **CreativeDemo!2026**. Other accounts: `admin`, `media_buyer`, `editor`, `reviewer`, `requester`, and `viewer`, each at `@demo.local` with the same local demo password. Demo seeding is refused when `DEBUG=False`. Never expose these accounts publicly.

For a clean machine or extracted ZIP, follow [Windows setup](docs/WINDOWS_LOCAL_SETUP.md). The ZIP excludes local secrets, databases, media, dependency folders, and test accounts; recreate demo data using `seed_demo`.

## What is implemented

- Email/session authentication, CSRF, password changes/reset, profiles, workspace memberships, roles and brand restrictions.
- Brands, products, campaigns, requests, multiple deliverables, assignments, a production board and scoped creative library.
- Explicit version submission/review/approval, feedback, conversations, preserved version history and creative lineage.
- Validated local uploads, storage identity, encrypted Google OAuth, Drive inventory/change sync and resumable Drive/YouTube transport.
- Deployments, historical performance observations, normalized metrics, fatigue signals, outcomes, experiments and context versions.
- Evidence tables, proposals, clips, content corrections, scoped search, UTM links and allow-listed automations.
- In-app notifications, audit/activity feeds, operations records, a durable SQLite job worker, backups and a guarded legacy importer.
- Arabic RTL interface, English and French locale selection, responsive layouts, Docker/Nginx configuration and operator documentation.

External operations require your provider credentials, API permissions and a running worker. No real external provider account was connected during development. Unsupported providers return a clear error and never create fake receipts.

## Stack and layout

Python 3.13; Django 5.2.17; Django REST Framework; SQLite with WAL/IMMEDIATE transactions; React 19; strict TypeScript; Vite 8; TanStack Query; React Hook Form/Zod; Tailwind 4. Exact dependency versions are locked in `backend/requirements.txt` and `frontend/package-lock.json`.

```text
backend/apps/   Bounded domain apps and explicit services
frontend/src/   React interface, forms, translations and API client
docs/           Architecture, setup, audit, scope and QA evidence
ops/            Dockerfiles and Nginx
scripts/        Local setup/start and clean packaging
```

## Verify

```powershell
cd backend
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check apps config tests
.venv\Scripts\python.exe manage.py check
.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
cd ..\frontend
npm.cmd test
npm.cmd run lint
npm.cmd run build
npm.cmd run e2e
```

Browser tests use installed Microsoft Edge and the local demo database. They intentionally add clearly named test records. Run against a disposable local database, never a live company database.

## Deployment and recovery

Use [deployment instructions](docs/DEPLOYMENT.md), [Google setup](docs/GOOGLE_SETUP.md), [provider capabilities](docs/PROVIDER_INTEGRATIONS.md), and [backup/restore](docs/BACKUP_RESTORE.md). Keep SQLite on local persistent storage, run one worker, and back up the encryption key separately.

Package a clean standalone archive with:

```powershell
backend\.venv\Scripts\python.exe scripts\package.py
```
