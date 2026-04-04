"""
backend/scripts/create_admin.py

Bootstrap script — promote an existing user to admin.

Usage (from backend/ directory):
    python scripts/create_admin.py --email kevin@tkverse.ca

Or interactively:
    python scripts/create_admin.py

WARNING: Run only in trusted environments.
         Never expose this script in production without proper access control.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Ensure backend package is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent.parent / ".env")

from api.config import settings  # noqa: E402 (after load_dotenv)
from api.database import engine  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker


AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def promote_to_admin(email: str) -> None:
    from api.models.user import User

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if not user:
            print(f"❌ User not found: {email}")
            print("   → Make sure the user registered first.")
            sys.exit(1)

        if user.is_admin:
            print(f"ℹ️  User {email} is already an admin. No change made.")
            return

        print(f"\nUser found:")
        print(f"  ID      : {user.id}")
        print(f"  Email   : {user.email}")
        print(f"  Name    : {user.full_name}")
        print(f"  Plan    : {user.plan}")
        print(f"  Active  : {user.is_active}")
        print(f"  Admin   : {user.is_admin}")

        confirm = input(f"\nPromote {email} to admin? [yes/no]: ").strip().lower()
        if confirm not in ("yes", "y"):
            print("Aborted.")
            sys.exit(0)

        user.is_admin = True
        await db.commit()
        await db.refresh(user)

        print(f"\n✅ {email} is now an admin.")
        print("   → They can access /api/v1/admin/* endpoints.")


async def list_admins() -> None:
    from api.models.user import User

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.is_admin == True))  # noqa: E712
        admins = result.scalars().all()
        if not admins:
            print("No admins found.")
            return
        print(f"\nCurrent admins ({len(admins)}):")
        for u in admins:
            print(f"  {u.email}  (id={u.id}, plan={u.plan})")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Promote a TKVerse user to admin",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/create_admin.py --email kevin@tkverse.ca
  python scripts/create_admin.py --list
        """,
    )
    parser.add_argument("--email", help="Email of the user to promote")
    parser.add_argument("--list", action="store_true", help="List all current admins")
    args = parser.parse_args()

    if args.list:
        asyncio.run(list_admins())
        return

    if args.email:
        email = args.email.strip().lower()
    else:
        email = input("Enter the email of the user to promote to admin: ").strip().lower()

    if not email:
        print("Email required.")
        sys.exit(1)

    asyncio.run(promote_to_admin(email))


if __name__ == "__main__":
    main()
