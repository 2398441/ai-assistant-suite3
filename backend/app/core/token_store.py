"""
Session token store (TinyDB).

One active token per user — reconnecting (or explicit logout) replaces the
previous token, invalidating any existing browser session for that email.

Tokens are 256-bit random URL-safe strings generated with secrets.token_urlsafe.
"""

import os
import secrets
import logging
from tinydb import TinyDB, Query

logger = logging.getLogger(__name__)

_DB_PATH = "data/token_store.json"
_db: TinyDB | None = None
_Q = Query()


def _get_db() -> TinyDB:
    global _db
    if _db is None:
        os.makedirs("data", exist_ok=True)
        _db = TinyDB(_DB_PATH)
    return _db


def create_token(email: str) -> str:
    """Generate a new session token for this email, replacing any existing one."""
    token = secrets.token_urlsafe(32)
    db = _get_db()
    record = {"email": email, "token": token}
    if db.get(_Q.email == email):
        db.update(record, _Q.email == email)
    else:
        db.insert(record)
    logger.debug("token_store | issued token for %s", email)
    return token


def validate_token(email: str, token: str | None) -> bool:
    """Return True if *token* matches the stored token for *email*."""
    if not token:
        return False
    record = _get_db().get(_Q.email == email)
    if not record:
        return False
    return secrets.compare_digest(record.get("token", ""), token)


def revoke_token(email: str) -> None:
    """Remove the session token for this user (logout)."""
    _get_db().remove(_Q.email == email)
    logger.debug("token_store | revoked token for %s", email)
