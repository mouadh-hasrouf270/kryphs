# Testing

Backend tests run with pytest-django using an isolated test SQLite database and temporary media. Test fixtures use a fast password hasher only inside tests. Real application passwords use Django's configured production hasher.

```powershell
cd backend
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check apps config tests
.venv\Scripts\python.exe manage.py check
.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.venv\Scripts\python.exe -m pip_audit --progress-spinner off
```

```powershell
cd frontend
npm.cmd ci
npm.cmd test
npm.cmd run lint
npm.cmd run typecheck
npm.cmd run build
npm.cmd audit
npm.cmd run e2e
```

Vitest tests use jsdom 26, compatible with the verified Node 22.20 runtime. Vitest explicitly includes only `src/**/*.test.{ts,tsx}`; Playwright owns `e2e/*.spec.ts`.

Playwright uses Microsoft Edge, starts/reuses Django on 8017 and Vite on 5173, and executes against a seeded **disposable** local database. It creates browser-labeled requests/creatives/deployments/experiments and a clearly named development Drive fixture. No test provider is registered in production. E2E Drive checks simulate metadata reconciliation; they are not a live Google test.

The suite covers the request/revision/approval journey, viewer denial, mobile RTL overflow, Drive ID retention, historical performance/outcomes and an experiment/variant learning. More exhaustive provider failure matrices, load tests, accessibility audits, complete locale coverage and real-account acceptance are still needed. See FINAL_QA_REPORT.md for verified counts rather than assuming all specification journeys are complete.
