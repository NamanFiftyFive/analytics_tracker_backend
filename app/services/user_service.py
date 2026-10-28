import asyncpg

from app.core.exceptions import BadRequestError, ConflictError
from app.core.security import PasswordService
from app.db.database import Executor
from app.repositories.user_repository import UserRepository


class UserService:
    @staticmethod
    async def get_or_create(
        conn: Executor, email: str, full_name: str | None, password: str | None
    ) -> tuple[asyncpg.Record, bool]:
        """Returns (user, created). An existing account is returned as-is; a new one needs a
        password. Call inside a transaction so the account is undone if a later step fails."""
        users = UserRepository(conn)
        user = await users.get_by_email(email)
        if user is not None:
            return user, False

        if not password:
            raise BadRequestError("No account exists for this email; a password is required to create one")
        try:
            user = await users.create(
                email=email, password_hash=PasswordService.hash(password), full_name=full_name
            )
        except asyncpg.UniqueViolationError:
            # Same email created by a concurrent request.
            raise ConflictError("An account with this email was just created; try again") from None
        return user, True
