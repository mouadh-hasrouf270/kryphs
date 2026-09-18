"""Production configuration acceptance against a new private SQLite database.

Runs actual Waitress and a worker. HTTPS is simulated at a trusted local proxy
boundary; this is not a certificate/DNS/provider acceptance test.
"""
from contextlib import closing
import json
import os
from pathlib import Path
import secrets
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import zipfile

import httpx
from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parents[1]


def main():
    checks = []
    with tempfile.TemporaryDirectory(prefix="cm-production-") as temporary:
        data = Path(temporary)
        with closing(socket.socket()) as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        env = os.environ | {"DJANGO_DEBUG": "false", "DJANGO_SECRET_KEY": secrets.token_urlsafe(64), "APP_ENCRYPTION_KEY": Fernet.generate_key().decode(), "DJANGO_ALLOWED_HOSTS": "127.0.0.1", "DJANGO_CSRF_TRUSTED_ORIGINS": f"https://127.0.0.1:{port}", "APP_BASE_URL": f"https://127.0.0.1:{port}", "DATABASE_PATH": str(data / "production.sqlite3"), "MEDIA_ROOT": str(data / "media"), "SECURE_HSTS_SECONDS": "31536000", "SMOKE_PASSWORD": secrets.token_urlsafe(24), "EMAIL_HOST": "", "PORT": str(port)}
        def manage(*args, source=None):
            result = subprocess.run([sys.executable,"manage.py",*args], cwd=ROOT/"backend",env=env,text=True,input=source,capture_output=True)
            if result.returncode:
                raise RuntimeError(result.stderr or result.stdout)
            return result.stdout
        manage("migrate","--noinput");checks.append("empty database migrated")
        manage("check","--deploy","--fail-level","WARNING");checks.append("production deploy checks passed")
        manage("collectstatic","--noinput")
        manage("shell", source="import os\nfrom apps.accounts.models import User\nUser.objects.create_superuser('release@example.test',os.environ['SMOKE_PASSWORD'])\n")
        log = (data / "runtime.log").open("w")
        web = worker = None
        def start_web():
            process = subprocess.Popen([sys.executable,"-m","waitress",f"--listen=127.0.0.1:{port}","--trusted-proxy=127.0.0.1","--trusted-proxy-headers=x-forwarded-proto","config.wsgi:application"],cwd=ROOT/"backend",env=env,stdout=log,stderr=log)
            for _ in range(150):
                if process.poll() is not None:
                    raise RuntimeError("Production web server failed; inspect startup configuration.")
                try:
                    if httpx.get(f"http://127.0.0.1:{port}/api/v1/health/").status_code == 200:
                        return process
                except httpx.HTTPError:
                    pass
                time.sleep(.2)
            process.terminate();process.wait();raise RuntimeError("Production startup timed out")
        try:
            web=start_web()
            worker=subprocess.Popen([sys.executable,"manage.py","run_worker"],cwd=ROOT/"backend",env=env,stdout=log,stderr=log)
            client=httpx.Client(base_url=f"http://127.0.0.1:{port}",headers={"X-Forwarded-Proto":"https","Origin":env["APP_BASE_URL"]})
            cookies={}
            def request(method,path,body=None):
                response=client.request(method,path,json=body,headers={"Cookie":"; ".join(f"{k}={v}" for k,v in cookies.items()),"X-CSRFToken":cookies.get("csrftoken","")})
                cookies.update(dict(response.cookies))
                assert response.status_code < 400, (path,response.status_code,response.text[:300])
                return response
            assert request("GET","/api/v1/ready/").json()["status"]=="ready"
            assert request("GET","/api/v1/auth/session/").json()=={"user":None}
            assert '<div id="root">' in request("GET","/").text
            checks.append("same-origin React, health, readiness and anonymous session served by Waitress")
            request("POST","/api/v1/auth/session/",{"email":"release@example.test","password":env["SMOKE_PASSWORD"]})
            ws=request("POST","/api/v1/workspaces/",{"name":"Release studio","slug":"release"}).json()["id"]
            suffix="?workspace="+ws
            brand=request("POST","/api/v1/brands/"+suffix,{"name":"Real brand","slug":"real"}).json()["id"]
            platforms=request("GET","/api/v1/platforms/").json()["results"][:2]
            created=request("POST","/api/v1/requests/"+suffix,{"title":"Release acceptance","brand":brand,"platforms":[p["id"] for p in platforms],"deliverables":[{"title":"Video","quantity":3}]}).json()
            assert len(created["platforms"])==2
            checks.append("production login, workspace and aggregate request with two platforms")
            manage("shell",source=f"from apps.common.models import Job\nJob.objects.create(workspace_id='{ws}',type='release_unknown_handler',max_attempts=1,idempotency_key='release-worker-proof')\n")
            for _ in range(80):
                with closing(sqlite3.connect(env["DATABASE_PATH"])) as db:
                    state=db.execute("select status from common_job where idempotency_key='release-worker-proof'").fetchone()[0]
                if state=='failed':break
                time.sleep(.2)
            assert state=='failed'
            checks.append("worker claimed and safely failed an unsupported test job")
            web.terminate();web.wait(timeout=15);web=start_web()
            persisted=request("GET",f"/api/v1/requests/{created['id']}/"+suffix).json()
            assert persisted["platforms"]==created["platforms"]
            checks.append("request and authenticated session persisted across web restart")
            archive=manage("backup_database","--directory",str(data/"backups")).strip().splitlines()[-1]
            manage("restore_database",archive,"--destination",str(data/"restored"))
            with closing(sqlite3.connect(data/"restored"/"database.sqlite3")) as restored:
                assert restored.execute("pragma integrity_check").fetchone()[0]=='ok'
                assert restored.execute("select count(*) from requests_app_creativerequest").fetchone()[0]==1
            with zipfile.ZipFile(archive) as backup:
                assert not any('.env' in name for name in backup.namelist())
            checks.append("production-format backup restored; integrity and request count verified")
            with closing(sqlite3.connect(env["DATABASE_PATH"])) as db:
                assert db.execute("pragma journal_mode").fetchone()[0]=='wal'
            checks.append("SQLite WAL verified")
        finally:
            for process in [web,worker]:
                if process and process.poll() is None:
                    process.terminate();process.wait(timeout=20)
            log.close()
    result={"status":"passed","checks":checks,"limitations":["No public DNS/TLS certificate test", "No live Google, Meta or SMTP credentials used"]}
    (ROOT/"docs"/"production-smoke.json").write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
