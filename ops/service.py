"""Single-node web + worker supervisor. No demo data and no generated secrets."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
children = []
stopped = False


def stop(*_):
    global stopped
    stopped = True


def main():
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    db = Path(os.environ["DATABASE_PATH"])
    db.parent.mkdir(parents=True, exist_ok=True)
    Path(os.environ["MEDIA_ROOT"]).mkdir(parents=True, exist_ok=True)
    for command in [["migrate", "--noinput"], ["check", "--deploy", "--fail-level", "WARNING"], ["collectstatic", "--noinput"]]:
        subprocess.run([sys.executable, "manage.py", *command], cwd=BACKEND, check=True)
    port = int(os.getenv("PORT", "8000"))
    # Managed platform TLS terminates at its trusted reverse proxy.
    web = [sys.executable, "-m", "waitress", f"--listen=0.0.0.0:{port}", "--threads=4", "--trusted-proxy=*", "--trusted-proxy-headers=x-forwarded-proto", "config.wsgi:application"]
    worker = [sys.executable, "manage.py", "run_worker"]
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        for command in [web, worker]:
            children.append(subprocess.Popen(command, cwd=BACKEND))
        backup_at = time.monotonic() + int(os.getenv("BACKUP_INTERVAL_SECONDS", "86400"))
        backup = None
        while not stopped:
            if any(child.poll() is not None for child in children):
                raise RuntimeError("A required process exited; stopping service for a clean restart.")
            if backup and backup.poll() is not None:
                if backup.returncode:
                    print("Nightly backup failed; review service logs.", file=sys.stderr, flush=True)
                else:
                    (db.parent / "last-backup-success.txt").write_text(str(time.time()))
                backup = None
            if time.monotonic() >= backup_at and backup is None:
                backup = subprocess.Popen([sys.executable, "manage.py", "backup_database", "--directory", str(db.parent / "backups")], cwd=BACKEND)
                backup_at = time.monotonic() + int(os.getenv("BACKUP_INTERVAL_SECONDS", "86400"))
            time.sleep(1)
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=55)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        if backup and backup.poll() is None:
            backup.wait(timeout=55)


if __name__ == "__main__":
    main()
