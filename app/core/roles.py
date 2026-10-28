from enum import StrEnum


class Role(StrEnum):
    """A member's role in an organization. Same values as the member_role enum in Postgres."""

    VIEWER = "viewer"
    ANALYST = "analyst"
    ADMIN = "admin"

    @property
    def rank(self) -> int:
        return _RANKS[self]

    def at_least(self, minimum: "Role") -> bool:
        """Role.ADMIN.at_least(Role.ANALYST) -> True: higher roles can do everything lower ones can."""
        return self.rank >= minimum.rank


_RANKS = {Role.VIEWER: 1, Role.ANALYST: 2, Role.ADMIN: 3}
