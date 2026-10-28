import pytest

from app.core.roles import Role
from app.schemas.client_response import ClientResponse


@pytest.mark.parametrize(
    ("role", "minimum", "allowed"),
    [
        (Role.ADMIN, Role.VIEWER, True),
        (Role.ADMIN, Role.ADMIN, True),
        (Role.ANALYST, Role.VIEWER, True),
        (Role.ANALYST, Role.ADMIN, False),
        (Role.VIEWER, Role.ANALYST, False),
        (Role.VIEWER, Role.VIEWER, True),
    ],
)
def test_role_at_least(role: Role, minimum: Role, allowed: bool):
    assert role.at_least(minimum) is allowed


def test_success_body_has_no_error_field():
    assert ClientResponse.success({"a": 1}).model_dump() == {"status": 200, "data": {"a": 1}}


def test_failure_body_has_no_data_field():
    assert ClientResponse.failure(404, "Not found").model_dump() == {"status": 404, "error": "Not found"}
