from datetime import date, datetime
from zoneinfo import ZoneInfo


# Clinic operations are based in India; expiry is a local calendar-date rule.
BUSINESS_TIMEZONE = ZoneInfo("Asia/Kolkata")


def business_today() -> date:
    """Return today's calendar date in the clinic business timezone."""
    return datetime.now(BUSINESS_TIMEZONE).date()
