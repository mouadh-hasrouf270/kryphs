import json

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from rest_framework.exceptions import ValidationError


def cipher():
    if not settings.APP_ENCRYPTION_KEY:
        raise ValidationError("APP_ENCRYPTION_KEY is required for integrations.")
    return Fernet(settings.APP_ENCRYPTION_KEY.encode())


def seal(value):
    return cipher().encrypt(json.dumps(value).encode()).decode()


def unseal(value):
    if not value:
        raise ValidationError("Provider credentials are not configured.")
    try:
        return json.loads(cipher().decrypt(value.encode()))
    except (InvalidToken, ValueError):
        raise ValidationError(
            "Integration credentials cannot be decrypted. Reconnect the provider."
        ) from None
