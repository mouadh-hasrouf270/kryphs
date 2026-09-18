import contextvars
import json
import logging
import uuid

correlation = contextvars.ContextVar("correlation", default="")
request_metadata = contextvars.ContextVar("request_metadata", default=None)


class CorrelationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.correlation_id = str(uuid.uuid4())
        token = correlation.set(request.correlation_id)
        meta_token = request_metadata.set(
            {
                "ip": request.META.get("REMOTE_ADDR") or None,
                "user_agent": request.META.get("HTTP_USER_AGENT", "")[:500],
            }
        )
        try:
            response = self.get_response(request)
            response["X-Request-ID"] = request.correlation_id
            response["Content-Security-Policy"] = (
                "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
            )
            response["Referrer-Policy"] = "same-origin"
            return response
        finally:
            correlation.reset(token)
            request_metadata.reset(meta_token)


class JsonFormatter(logging.Formatter):
    def format(self, record):
        # Do not serialize request bodies, cookies, URLs or provider exceptions.
        return json.dumps(
            {
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
                "correlation_id": correlation.get(),
            }
        )
