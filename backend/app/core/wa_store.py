"""
Persistent WhatsApp settings store (TinyDB).

Schema per record:
  { "email": "user@example.com", "whatsapp_number": "+91...", "enabled": true }
"""

import os
import logging
from tinydb import TinyDB, Query

logger = logging.getLogger(__name__)

_DB_PATH = "data/wa_settings.json"
_db: TinyDB | None = None
_User = Query()


def _get_db() -> TinyDB:
    global _db
    if _db is None:
        os.makedirs("data", exist_ok=True)
        _db = TinyDB(_DB_PATH)
    return _db


def save_wa_settings(email: str, whatsapp_number: str, enabled: bool) -> None:
    """Upsert WA settings for a user."""
    db = _get_db()
    record = {"email": email, "whatsapp_number": whatsapp_number, "enabled": enabled}
    if db.get(_User.email == email):
        db.update(record, _User.email == email)
    else:
        db.insert(record)
    logger.debug("wa_store | saved settings for %s (enabled=%s)", email, enabled)


def load_wa_settings(email: str) -> tuple[str, bool]:
    """Return (whatsapp_number, enabled) for a user, or ("", False) if not found."""
    record = _get_db().get(_User.email == email)
    if record is None:
        return "", False
    return record.get("whatsapp_number", ""), record.get("enabled", False)
