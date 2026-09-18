# Windows local setup

Install Python 3.13 from https://www.python.org/downloads/windows/ and a supported Node 22 LTS release from https://nodejs.org/. This build was verified with Python 3.13 and Node 22.20.0. Microsoft Edge is used for Playwright.

Open PowerShell in the extracted `creative-manager` directory:

```powershell
py -3.13 -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
backend\.venv\Scripts\python.exe scripts\setup_local.py
cd backend
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py createsuperuser
.venv\Scripts\python.exe manage.py seed_demo
.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8017
```

The setup script creates `.env` only when absent, generates independent random signing/encryption keys, and enables local DEBUG. It never prints the keys. Local password reset emails are saved privately under `backend/mail`; configure SMTP for real delivery. Do not commit that folder.

In a second PowerShell window:

```powershell
cd frontend
npm.cmd ci
npm.cmd run dev
```

In a third window:

```powershell
cd backend
.venv\Scripts\python.exe manage.py run_worker
```

Visit http://127.0.0.1:5173. Use the language selector to choose Arabic, English or French. Demo credentials are in README. The demo is fictional and has no live provider connections.

Optional venv activation:

```powershell
cd backend
.venv\Scripts\Activate.ps1
python manage.py check
```

If PowerShell blocks activation scripts, use the explicit `.venv\Scripts\python.exe` commands above; no execution-policy change is necessary. In Command Prompt, use `.venv\Scripts\activate.bat`.

After setup, `scripts\start_local.ps1` can launch the three development processes with hidden windows and log files. Do not run duplicate workers. Use Ctrl+C in foreground terminals to stop services. For helper-launched processes, stop only processes whose command lines point to this project.

## Tests

```powershell
cd backend
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check apps config tests
cd ..\frontend
npm.cmd test
npm.cmd run typecheck
npm.cmd run lint
npm.cmd run build
npm.cmd run e2e
```

If port 5173 is occupied, stop only your existing CreativeManager Vite process or choose another port and update CSRF trusted origins. The configured backend port is 8017. Port 8000 is reserved for the internal Docker service and is not required by native development.
