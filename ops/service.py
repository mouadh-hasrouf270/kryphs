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

    # Prepare database first.
    subprocess.run(
        [sys.executable, "manage.py", "migrate", "--noinput"],
        cwd=BACKEND,
        check=True,
    )

    # Optional first-admin bootstrap for managed deployments such as Render.
    #
    # If DJANGO_SUPERUSER_EMAIL and DJANGO_SUPERUSER_PASSWORD are present,
    # create the user if needed or promote/update the existing user.
    #
    # The bootstrap command is intentionally kept on one line to avoid
    # indentation errors when passed to `manage.py shell -c`.
    admin_email = os.getenv("DJANGO_SUPERUSER_EMAIL", "").strip().lower()
    admin_password = os.getenv("DJANGO_SUPERUSER_PASSWORD", "")

    if admin_email and admin_password:
        bootstrap_admin = (
            "import os; "
            "from django.contrib.auth import get_user_model; "
            "User=get_user_model(); "
            "email=os.environ['DJANGO_SUPERUSER_EMAIL'].strip().lower(); "
            "password=os.environ['DJANGO_SUPERUSER_PASSWORD']; "
            "user,created=User.objects.get_or_create(email=email); "
            "user.is_staff=True; "
            "user.is_superuser=True; "
            "user.is_active=True; "
            "user.set_password(password); "
            "user.save(); "
            "print('SUPERUSER_READY:', email)"
        )

        subprocess.run(
            [sys.executable, "manage.py", "shell", "-c", bootstrap_admin],
            cwd=BACKEND,
            check=True,
        )

    # Production validation and static assets.
    for command in [
        ["check", "--deploy", "--fail-level", "WARNING"],
        ["collectstatic", "--noinput"],
    ]:
        subprocess.run(
            [sys.executable, "manage.py", *command],
            cwd=BACKEND,
            check=True,
        )

    port = int(os.getenv("PORT", "8000"))

    # Managed platform TLS terminates at its trusted reverse proxy.
    web = [
        sys.executable,
        "-m",
        "waitress",
        f"--listen=0.0.0.0:{port}",
        "--threads=4",
        "--trusted-proxy=*",
        "--trusted-proxy-headers=x-forwarded-proto",
        "config.wsgi:application",
    ]
    worker = [sys.executable, "manage.py", "run_worker"]

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    backup = None
    try:
        for command in [web, worker]:
            children.append(subprocess.Popen(command, cwd=BACKEND))

        backup_at = time.monotonic() + int(
            os.getenv("BACKUP_INTERVAL_SECONDS", "86400")
        )

        while not stopped:
            if any(child.poll() is not None for child in children):
                raise RuntimeError(
                    "A required process exited; stopping service for a clean restart."
                )

            if backup and backup.poll() is not None:
                if backup.returncode:
                    print(
                        "Nightly backup failed; review service logs.",
                        file=sys.stderr,
                        flush=True,
                    )
                else:
                    (db.parent / "last-backup-success.txt").write_text(
                        str(time.time())
                    )
                backup = None

            if time.monotonic() >= backup_at and backup is None:
                backup = subprocess.Popen(
                    [
                        sys.executable,
                        "manage.py",
                        "backup_database",
                        "--directory",
                        str(db.parent / "backups"),
                    ],
                    cwd=BACKEND,
                )
                backup_at = time.monotonic() + int(
                    os.getenv("BACKUP_INTERVAL_SECONDS", "86400")
                )

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
            try:
                backup.wait(timeout=55)
            except subprocess.TimeoutExpired:
                backup.kill()
                backup.wait()


if __name__ == "__main__":
    main()
