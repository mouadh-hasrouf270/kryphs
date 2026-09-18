from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_handler


def exception_handler(exc, context):
    from apps.storage.google import ProviderFailure

    if isinstance(exc, ProviderFailure):
        return Response({"detail": str(exc)}, status=400)
    if isinstance(exc, DjangoValidationError):
        exc = ValidationError(getattr(exc, "message_dict", exc.messages))
    if isinstance(exc, IntegrityError):
        return Response(
            {"detail": "This operation conflicts with an existing record or a data constraint."},
            status=409,
        )
    response = drf_handler(exc, context)
    if response is not None:
        return response
    import logging
    import traceback

    from apps.common.middleware import correlation

    # Frames give operators the failure location without dumping exception
    # messages, provider bodies or local variables containing credentials.
    logging.getLogger(__name__).error(
        "Unhandled %s\n%s", type(exc).__name__, "".join(traceback.format_tb(exc.__traceback__))
    )
    return Response(
        {
            "detail": "An unexpected error occurred. Contact your administrator with the request ID.",
            "request_id": correlation.get(),
        },
        status=500,
    )
