# Deployment

Complete the QA/limitations review before a company rollout. The application is not certified as full specification parity.

## Docker

1. Copy `.env.example` to `.env` on the deployment host.
2. Generate strong independent signing and Fernet keys. Store them in your secret manager and `.env`, never in source control or logs.
3. Set `DJANGO_DEBUG=false`, exact allowed hosts and trusted HTTPS origins, SMTP, and optional provider settings.
4. Use a local persistent disk for Docker volume `data`. Do not place SQLite on NFS, SMB, a distributed filesystem or a synced cloud folder.
5. Build and initialize:

```powershell
docker compose build
docker compose run --rm init
docker compose run --rm web python manage.py createsuperuser
docker compose up -d web worker nginx
docker compose exec web python manage.py check --deploy
```

Nginx binds only **127.0.0.1:8080**. Put a trusted HTTPS reverse proxy in front of it, forwarding the public Host unchanged. The supplied internal Nginx marks the Django request as HTTPS; do not expose that internal port directly to untrusted clients. Terminate TLS and redirect HTTP to HTTPS at the public proxy.

`init` migrates the database and collects admin static assets. Web uses Waitress; worker runs `run_worker`. Both mount the same local SQLite/media volume. Keep one worker. Back up before updates; rerun init after rebuilding. Never run demo seeding in production.

```powershell
docker compose logs --tail 100 web worker
docker compose exec web python manage.py backup_database --directory /data/backups --retain 14
docker compose exec web python manage.py check_database
docker compose exec web python manage.py scan_deadlines
```

Schedule backup nightly and deadline scanning hourly with the host scheduler. Copy backups off-host securely. Keep the encryption key backup separate.

## Native Windows production

Build the frontend and use a trusted HTTPS static/reverse proxy such as IIS or Nginx. Proxy `/api/` and `/admin/` to a supervised Waitress service bound to loopback. Serve `frontend/dist` and collected admin static files; **do not** serve `backend/media` directly.

```powershell
cd frontend
npm.cmd ci
npm.cmd run build
cd ..\backend
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py collectstatic --noinput
.venv\Scripts\waitress-serve.exe --listen=127.0.0.1:8017 --threads=4 config.wsgi:application
```

Run `run_worker` as a second supervised service. Set production environment variables for both processes. `runserver` and Vite's dev server are for local development only.

## Release checklist

- [ ] Review every unresolved item in KNOWN_LIMITATIONS.md.
- [ ] Verify production allowed hosts, trusted CSRF origins, DEBUG false, unique keys and secure cookies.
- [ ] Configure HTTPS, then enable HSTS and validate redirects.
- [ ] Disable/deactivate all demo accounts and remove demo data from production setup.
- [ ] Create real users, memberships and brand restrictions; exercise cross-brand denial.
- [ ] Verify SMTP reset delivery and provider permissions using actual accounts.
- [ ] Verify real Drive/YouTube/Meta operations on test assets before live campaigns.
- [ ] Schedule backups and deadline scanning; rehearse restore with the original encryption key.
- [ ] Run all local quality gates and inspect dependency audits.
- [ ] Verify monitoring, disk space, failed/stale jobs, upload limits and a single worker.
