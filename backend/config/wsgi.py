import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()

from django.conf import settings
from whitenoise import WhiteNoise

application = WhiteNoise(application, root=str(settings.STATIC_ROOT), prefix="static/")
if (settings.FRONTEND_DIST / "assets").is_dir():
    application.add_files(str(settings.FRONTEND_DIST / "assets"), prefix="assets/")
