"""Metadata-only HTTP diagnostics and redaction for application log handlers."""
import copy
import logging
import re

_URL = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_EMAIL = re.compile(r"[A-Za-z0-9_.+%-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_JWT = re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")
_BEARER = re.compile(r"\b(?:Bearer\s+)+[^\s,;\"']+", re.IGNORECASE)
_CREDENTIAL = re.compile(
    r"((?:access[_-]?token|refresh[_-]?token|session[_-]?token|api[_-]?key|password|authorization|cookie|cf_clearance|secret)\b[\"']?\s*[:=]\s*)"
    r"(?:\"[^\"]*\"|'[^']*'|[^\s,;}]+)", re.IGNORECASE,
)


def redact_message(message):
    message = _URL.sub("[url]", message)
    message = _EMAIL.sub("[email]", message)
    message = _JWT.sub("[credential]", message)
    message = _BEARER.sub("Bearer [credential]", message)
    message = _CREDENTIAL.sub(r"\1[credential]", message)
    return message.replace("\r", "\\r").replace("\n", "\\n")


class SafeFormatter(logging.Formatter):
    def format(self, record):
        safe = copy.copy(record)
        if record.name == "access":
            safe.msg = record.getMessage().replace("\r", "\\r").replace("\n", "\\n")
            safe.args = ()
        elif record.name.startswith(("django.server", "django.request", "django.security")):
            status = getattr(record, "status_code", None)
            if not isinstance(status, int) or not 100 <= status <= 599:
                status = 500 if record.levelno >= logging.ERROR else 400
            safe.msg = "HTTP request diagnostic status=%s"
            safe.args = (status,)
        elif record.name.startswith("django.db.backends"):
            safe.msg = "Database operation diagnostic"
            safe.args = ()
        else:
            safe.msg = redact_message(record.getMessage())
            safe.args = ()
        # Exception strings and tracebacks can contain request bodies or SQL values.
        if record.exc_info and record.exc_info[0]:
            safe.msg += " error_type=" + record.exc_info[0].__name__
        safe.exc_info = None
        safe.exc_text = None
        safe.stack_info = None
        return super().format(safe)


class AccessLogMiddleware:
    """Log the method, path and query names; never read or log request bodies."""
    def __init__(self, get_response):
        self.get_response = get_response
        self.logger = logging.getLogger("access")

    def __call__(self, request):
        response = self.get_response(request)
        from urllib.parse import urlencode
        from django.conf import settings
        import hmac
        internal_health = (
            request.path in ("/0x/user/version-cfg", "/0x/user/login-guard")
            and (request.path == "/0x/user/login-guard" or request.META.get("HTTP_X_MIRROR_HEALTHCHECK") == "1")
            and hmac.compare_digest(request.META.get("HTTP_X_GATEWAY_SECRET", ""), settings.GATEWAY_ADMIN_SECRET)
        )
        if not internal_health:
            names = sorted(request.GET.keys())[:50]
            query = urlencode([(name[:80], "*") for name in names], safe="*")
            match = getattr(request, "resolver_match", None)
            route = getattr(match, "route", None)
            path = ("/" + route.lstrip("/"))[:1500] if route else request.path[:1500]
            fields = getattr(request, "_access_parameter_names", [])
            field_names = urlencode([(name, "*") for name in fields], safe="*")
            self.logger.info("%s %s%s%s status=%s", request.method[:16], path,
                             "?" + query if query else "", " fields=" + field_names if field_names else "", response.status_code)
        return response
