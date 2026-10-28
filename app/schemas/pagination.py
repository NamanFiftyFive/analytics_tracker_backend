from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """One page of a list. Next page: offset + limit, while offset + limit < total."""

    items: list[T]
    total: int
    limit: int
    offset: int
