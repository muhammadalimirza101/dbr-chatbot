"""Create (or reset the password of) an admin user.

Usage (from backend/):
    .\\.venv\\Scripts\\python -m scripts.create_admin admin@example.com "Full Name"

The password is read from a hidden prompt — never from argv, so it can't
land in shell history or process lists.
"""

import asyncio
import getpass
import sys

from sqlalchemy import select

from app.database import async_session_factory, engine
from app.models import User
from app.models.enums import UserRole
from app.services.audit import record_audit
from app.services.auth import hash_password


async def main(email: str, full_name: str) -> None:
    password = getpass.getpass("Password (min 8 chars): ")
    if len(password) < 8:
        print("Password must be at least 8 characters.")
        sys.exit(1)
    if password != getpass.getpass("Confirm password: "):
        print("Passwords do not match.")
        sys.exit(1)

    async with async_session_factory() as session:
        existing = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if existing:
            existing.password_hash = hash_password(password)
            existing.role = UserRole.ADMIN
            existing.is_active = True
            action, user = "admin_password_reset", existing
        else:
            user = User(
                email=email,
                password_hash=hash_password(password),
                full_name=full_name,
                role=UserRole.ADMIN,
            )
            session.add(user)
            await session.flush()
            action = "admin_created"
        await record_audit(
            session, user_id=user.id, action=action, entity_type="user",
            entity_id=user.id,
        )
        await session.commit()
        print(f"{action}: {email} (id={user.id})")
    await engine.dispose()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    asyncio.run(main(sys.argv[1].lower(), sys.argv[2]))
