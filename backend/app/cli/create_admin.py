import argparse
from getpass import getpass

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import get_engine
from app.models import User, UserRole
from app.services.security import hash_password


def main() -> None:
    parser = argparse.ArgumentParser(description="Provision a MedShare platform administrator.")
    parser.add_argument("email", help="Email address for the administrator account")
    parser.add_argument("--name", required=True, help="Administrator's display name")
    args = parser.parse_args()

    try:
        email = str(TypeAdapter(EmailStr).validate_python(args.email.strip())).lower()
    except ValidationError:
        parser.error("email must be a valid email address")
    if len(email) > 320:
        parser.error("email must be at most 320 characters")
    name = args.name.strip()
    if not name or len(name) > 120:
        parser.error("name must be between 1 and 120 characters")
    password = getpass("Administrator password: ")
    confirmation = getpass("Confirm password: ")
    if password != confirmation:
        parser.error("passwords do not match")
    if len(password) < 12:
        parser.error("administrator password must be at least 12 characters")
    if len(password.encode("utf-8")) > 72:
        parser.error("administrator password must not exceed 72 UTF-8 bytes")

    with Session(get_engine()) as db:
        if db.scalar(select(User.id).where(User.email == email)) is not None:
            parser.error("an account with that email already exists")
        admin = User(
            name=name,
            email=email,
            password_hash=hash_password(password),
            role=UserRole.ADMIN,
            is_active=True,
        )
        db.add(admin)
        db.commit()
    print(f"Provisioned ADMIN account for {email}")


if __name__ == "__main__":
    main()
