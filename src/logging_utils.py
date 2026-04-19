from __future__ import annotations

import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from starlette.responses import Response


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": getattr(record, "service", os.getenv("SERVICE_NAME", "unknown")),
        }

        # Include selected structured fields when present.
        for key in (
            "request_id",
            "method",
            "path",
            "status_code",
            "duration_ms",
            "client_ip",
            "node_id",
        ):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value

        return json.dumps(payload, separators=(",", ":"))


def setup_json_logging(service_name: str) -> None:
    os.environ["SERVICE_NAME"] = service_name
    root = logging.getLogger()
    root.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())

    # Avoid stacking handlers when apps reload.
    if root.handlers:
        root.handlers.clear()

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)


def install_request_logging(app: FastAPI, logger: logging.Logger, service_name: str) -> None:
    @app.middleware("http")
    async def request_logging_middleware(request: Request, call_next) -> Response:
        request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
        start = time.perf_counter()

        response = await call_next(request)

        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        client_ip = request.client.host if request.client else "unknown"

        logger.info(
            "request_complete",
            extra={
                "service": service_name,
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
                "client_ip": client_ip,
            },
        )
        response.headers["x-request-id"] = request_id
        return response
