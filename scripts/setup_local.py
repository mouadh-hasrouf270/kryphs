"""Create local-only development configuration without overwriting existing secrets."""
from pathlib import Path
import secrets
from cryptography.fernet import Fernet

root = Path(__file__).resolve().parents[1]
path = root / '.env'
if path.exists():
    print('.env exists; preserved.')
else:
    path.write_text(f'DJANGO_DEBUG=true\nDJANGO_SECRET_KEY={secrets.token_urlsafe(64)}\nAPP_ENCRYPTION_KEY={Fernet.generate_key().decode()}\nDJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,testserver\nEMAIL_BACKEND=django.core.mail.backends.filebased.EmailBackend\n', encoding='utf-8')
    print('Created local .env with independent random keys.')
