from collections.abc import Mapping
from typing import Any, Generic, TypeVar

from fastapi import status as http_status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, SerializerFunctionWrapHandler, model_serializer

T = TypeVar("T")


class ClientResponse(BaseModel, Generic[T]):
    """The one shape every API response has.

    Success:  {"status": 200, "data": {...}}
    Error:    {"status": 404, "error": "Project not found"}

    `status` always equals the HTTP status code. A success response never
    contains `error`, and an error response never contains `data`.
    """

    status: int
    data: T | None = None
    error: str | None = None

    @classmethod
    def success(cls, data: Any = None, status: int = http_status.HTTP_200_OK) -> "ClientResponse[Any]":
        return cls(status=status, data=data)

    @classmethod
    def failure(cls, status: int, error: str) -> "ClientResponse[Any]":
        return cls(status=status, error=error)

    @property
    def is_error(self) -> bool:
        return self.error is not None

    def to_json_response(self, headers: Mapping[str, str] | None = None) -> JSONResponse:
        """For exception handlers, which must return a Response themselves."""
        return JSONResponse(self.model_dump(mode="json"), status_code=self.status, headers=headers)

    @model_serializer(mode="wrap")
    def _drop_unused_field(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        body = handler(self)
        body.pop("data" if self.is_error else "error", None)
        return body
