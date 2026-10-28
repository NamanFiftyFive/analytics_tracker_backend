"""Turns every kind of error into a ClientResponse error body: {"status": ..., "error": ...}."""

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.core.exceptions import AppError
from app.schemas.client_response import ClientResponse

logger = logging.getLogger(__name__)


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Errors raised on purpose by services: ConflictError, NotFoundError, ..."""
    return ClientResponse.failure(exc.status_code, exc.detail).to_json_response(exc.headers)


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Bad or missing fields in the request (422)."""
    return ClientResponse.failure(
        status.HTTP_422_UNPROCESSABLE_CONTENT, format_validation_errors(exc)
    ).to_json_response()


async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Framework errors such as 404 unknown URL or 405 wrong method."""
    return ClientResponse.failure(exc.status_code, str(exc.detail)).to_json_response(exc.headers)


async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Bugs. Full details go to the server log, never to the client."""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return ClientResponse.failure(
        status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal server error"
    ).to_json_response()


def format_validation_errors(exc: RequestValidationError) -> str:
    """'email: value is not a valid email address; password: Field required'"""
    messages = []
    for err in exc.errors():
        if err["type"] == "json_invalid":
            return "Request body is not valid JSON"
        # loc looks like ("body", "password") or ("query", "limit"); drop the location prefix.
        field = ".".join(str(part) for part in err["loc"][1:]) or str(err["loc"][0])
        messages.append(f"{field}: {err['msg']}")
    return "; ".join(messages)


# Which handler deals with which exception type. Typed as Any because Starlette's
# hints expect every handler to accept a plain Exception, although it passes the matching type.   
EXCEPTION_HANDLERS: dict[type[Exception], Any] = {
    AppError: app_error_handler,
    RequestValidationError: validation_error_handler,
    HTTPException: http_error_handler,
    Exception: unexpected_error_handler,
}


def register_exception_handlers(app: FastAPI) -> None:
    for exception_type, handler in EXCEPTION_HANDLERS.items():
        app.add_exception_handler(exception_type, handler)
