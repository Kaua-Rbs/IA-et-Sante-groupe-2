"""Structured logs and access trail (RGPD art. 32, AI Act art. 12).

Every API call is written to stdout as one JSON line: who (username from the verified
token), from where (client address forwarded by the front), what (method, route template
and its identifiers), result (status) and when. Request bodies and query strings are never
logged: they may hold patient data. On the server, stdout goes to the persistent journal.
"""

import json
import logging
import sys
import time
import uuid
from datetime import datetime, timezone

from fastapi import Request

from api.accounts.security import token_subject
from api.config import client_address

audit_logger = logging.getLogger("kyst.audit")

# Attributes of every LogRecord: the others come from `extra=` and are written as fields
_RECORD_FIELDS = set(vars(logging.makeLogRecord({}))) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        entry.update({k: v for k, v in vars(record).items() if k not in _RECORD_FIELDS})
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str, ensure_ascii=False)


def configure_logging() -> None:
    """JSON lines on stdout for the application and uvicorn errors."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True
    # Replaced by the access trail below, which knows the user and the real client address
    logging.getLogger("uvicorn.access").disabled = True
    logging.getLogger("httpx").setLevel(logging.WARNING)


def _bearer(request: Request) -> str | None:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    return token if scheme.lower() == "bearer" and token else None


async def access_log(request: Request, call_next):
    """Middleware: one `http.access` entry per request, including failed ones."""
    request_id = uuid.uuid4().hex
    start = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        route = request.scope.get("route")
        token = _bearer(request)
        audit_logger.info("http.access", extra={
            "event": "http.access",
            "request_id": request_id,
            "user": token_subject(token) if token else None,
            "client": client_address(request),
            "method": request.method,
            # Template (/patients/{patient_id}) and identifiers: never the query string
            "route": getattr(route, "path", None) or request.url.path,
            "params": dict(request.path_params) or None,
            "status": status,
            "duration_ms": round((time.perf_counter() - start) * 1000, 1),
        })


def audit(event: str, request: Request | None = None, **fields) -> None:
    """Business event (login, failed login...) added to the trail."""
    if request is not None:
        fields.setdefault("client", client_address(request))
    audit_logger.info(event, extra={"event": event, **fields})
