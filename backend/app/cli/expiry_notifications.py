"""Optionally create persistent clinic expiry reminders in a maintenance run.

Pharmacists receive reminders through authenticated dashboard requests; this
command is not required for dashboard delivery.
"""
from sqlalchemy.orm import Session

from app.db.database import get_engine
from app.services.notifications import notify_expiry_reminders


def main() -> None:
    with Session(get_engine()) as db:
        examined = notify_expiry_reminders(db)
    print(f"Expiry reminders checked for {examined} inventory records.")


if __name__ == "__main__":
    main()
