from django.conf import settings
from django.http import FileResponse, Http404


def index(request):
    path = settings.FRONTEND_DIST / "index.html"
    if not path.is_file():
        raise Http404("Build the React application before starting production.")
    response = FileResponse(path.open("rb"), content_type="text/html")
    response["Cache-Control"] = "no-cache"
    return response
