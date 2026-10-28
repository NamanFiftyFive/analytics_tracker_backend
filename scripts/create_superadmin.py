"""Make a user the platform super admin (or remove the flag). Run from backend/:

    .venv/bin/python -m scripts.create_superadmin you@example.com           # promote, or create + promote
    .venv/bin/python -m scripts.create_superadmin you@example.com --revoke  # remove super admin

If the email has no account yet, you are asked for a name and password to create it.
This is the only way to create a super admin; there is deliberately no API endpoint for it.
"""

import argparse
import asyncio
import getpass
import sys

from app.core.security import PasswordService
from app.db.database import db
from app.repositories.user_repository import UserRepository


async def main(email: str, revoke: bool) -> int:
    await db.connect()
    try:
        async with db.transaction() as conn:
            users = UserRepository(conn)
            user = await users.get_by_email(email)

            if revoke:
                if user is None:
                    print(f"No account found for {email}")
                    return 1
                await users.set_superadmin(user["id"], False)
                print(f"{user['email']} is no longer a super admin")
                return 0

            if user is None:
                print(f"No account for {email}; creating one.")
                full_name = input("Full name: ").strip() or None
                password = getpass.getpass("Password (min 8 characters): ")
                if len(password) < 8:
                    print("Password must be at least 8 characters")
                    return 1
                user = await users.create(email, PasswordService.hash(password), full_name)

            await users.set_superadmin(user["id"], True)
            print(f"{user['email']} is now a super admin")
            return 0
    finally:
        await db.disconnect()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Grant or revoke platform super admin.")
    parser.add_argument("email")
    parser.add_argument("--revoke", action="store_true", help="remove super admin instead")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.email, args.revoke)))
