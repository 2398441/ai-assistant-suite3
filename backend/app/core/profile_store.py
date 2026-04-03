"""
Persistent user profile cache (TinyDB).

Survives backend restarts so the first request after a restart does not
need to re-fetch timezone, locale, calendars, frequent contacts, etc.
from provider APIs.

Schema per record:
  {
    "email":        "user@example.com",
    "display_name": "Alice Smith",
    "provider":     "gmail" | "outlook",
    "profile":      { timezone, locale, calendars, frequent_contacts, ... },
    "fetched_at":   "2026-03-13T08:00:00"   ← UTC ISO string
  }
"""

import os
import logging
from datetime import datetime
from tinydb import TinyDB, Query

logger = logging.getLogger(__name__)

_DB_PATH = "data/profile_cache.json"
_db: TinyDB | None = None
_User = Query()


def _get_db() -> TinyDB:
    global _db
    if _db is None:
        os.makedirs("data", exist_ok=True)
        _db = TinyDB(_DB_PATH)
    return _db


def save_profile(
    email: str,
    display_name: str | None,
    profile: dict,
    provider: str = "gmail",
) -> None:
    """Upsert the cached profile for a user."""
    db = _get_db()
    record = {
        "email":        email,
        "display_name": display_name or "",
        "provider":     provider,
        "profile":      profile,
        "fetched_at":   datetime.utcnow().isoformat(),
    }
    if db.get(_User.email == email):
        db.update(record, _User.email == email)
    else:
        db.insert(record)
    logger.debug("profile_store | saved %s profile for %s", provider, email)


def clear_profile(email: str) -> None:
    """Remove the cached profile for a user (called on logout)."""
    _get_db().remove(_User.email == email)
    logger.debug("profile_store | cleared profile for %s", email)


def load_profile(email: str) -> tuple[str | None, dict, datetime | None, str]:
    """
    Return (display_name, profile, fetched_at, provider) for a user.
    Returns (None, {}, None, "gmail") if no cached record exists.
    """
    record = _get_db().get(_User.email == email)
    if record is None:
        return None, {}, None, "gmail"

    display_name = record.get("display_name") or None
    profile      = record.get("profile", {})
    provider     = record.get("provider", "gmail")
    fetched_at   = None
    raw_ts       = record.get("fetched_at")
    if raw_ts:
        try:
            fetched_at = datetime.fromisoformat(raw_ts)
        except Exception:
            pass

    return display_name, profile, fetched_at, provider
