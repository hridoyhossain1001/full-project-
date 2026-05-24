import argparse
import asyncio
import csv
from pathlib import Path
import secrets
import sys

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.database import AsyncSessionLocal
from app.models.client import Client
from app.models.client_user import ClientUser
from app.services.auth_service import hash_password


def random_email(client_id: int) -> str:
    return f"client-{client_id}-{secrets.token_hex(4)}@client.buykori.app"


def random_password() -> str:
    return f"Bk-{secrets.token_urlsafe(12)}-7"


async def run(apply: bool, csv_path: str | None) -> int:
    rows: list[dict[str, str]] = []

    async with AsyncSessionLocal() as db:
        clients_r = await db.execute(select(Client).order_by(Client.id))
        clients = clients_r.scalars().all()

        for client in clients:
            user_r = await db.execute(
                select(ClientUser).where(ClientUser.client_id == client.id)
            )
            if user_r.scalar_one_or_none():
                continue

            email = random_email(client.id)
            password = random_password()
            rows.append({
                "client_id": str(client.id),
                "client_name": client.name,
                "email": email,
                "password": password,
            })

            if apply:
                db.add(ClientUser(
                    client_id=client.id,
                    email=email,
                    password_hash=hash_password(password),
                    full_name=f"{client.name} Owner",
                    role="owner",
                    is_active=True,
                    email_verified=True,
                ))

        if apply:
            await db.commit()

    if csv_path:
        with open(csv_path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["client_id", "client_name", "email", "password"])
            writer.writeheader()
            writer.writerows(rows)
    else:
        writer = csv.DictWriter(sys.stdout, fieldnames=["client_id", "client_name", "email", "password"])
        writer.writeheader()
        writer.writerows(rows)

    action = "created" if apply else "would_create"
    print(f"{action}={len(rows)}", file=sys.stderr)
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create email/password portal users for existing clients that do not have one."
    )
    parser.add_argument("--apply", action="store_true", help="Write users to the configured database.")
    parser.add_argument("--csv", help="Write generated credentials to a CSV file.")
    args = parser.parse_args()

    if not args.apply:
        print("Dry run only. Re-run with --apply to write users.", file=sys.stderr)

    asyncio.run(run(args.apply, args.csv))


if __name__ == "__main__":
    main()
