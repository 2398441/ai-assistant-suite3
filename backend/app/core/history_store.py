"""
Persistent chat history store (TinyDB).

Stores conversation messages per user per agent type so context survives
backend restarts.  Keyed by "email:agent_type" for fast single-record
lookups.

Schema per record:
  {
    "key":        "user@example.com:workspace",
    "email":      "user@example.com",
    "agent_type": "workspace",
    "messages":   [ ... Anthropic message dicts ... ],
    "updated_at": "2026-03-17T08:00:00"
  }
"""

import os
import logging
from datetime import datetime
from typing import Any
from tinydb import TinyDB, Query

logger = logging.getLogger(__name__)

_DB_PATH = "data/history_store.json"
_db: TinyDB | None = None
_Q = Query()


def _get_db() -> TinyDB:
    global _db
    if _db is None:
        os.makedirs("data", exist_ok=True)
        _db = TinyDB(_DB_PATH)
    return _db


def _key(email: str, agent_type: str) -> str:
    return f"{email}:{agent_type}"


def save_history(email: str, agent_type: str, messages: list[dict[str, Any]]) -> None:
    """Upsert conversation history for a user + agent pair."""
    db = _get_db()
    k = _key(email, agent_type)
    record = {
        "key":        k,
        "email":      email,
        "agent_type": agent_type,
        "messages":   messages,
        "updated_at": datetime.utcnow().isoformat(),
    }
    if db.get(_Q.key == k):
        db.update(record, _Q.key == k)
    else:
        db.insert(record)
    logger.debug("history_store | saved %d msgs for %s/%s", len(messages), email, agent_type)


def load_history(email: str, agent_type: str) -> list[dict[str, Any]]:
    """Return stored messages for a user + agent pair, or [] if none."""
    record = _get_db().get(_Q.key == _key(email, agent_type))
    return record.get("messages", []) if record else []


def clear_history(email: str, agent_type: str | None = None) -> None:
    """Clear history for one agent, or all agents for this user if agent_type is None."""
    db = _get_db()
    if agent_type:
        db.remove(_Q.key == _key(email, agent_type))
    else:
        db.remove(_Q.email == email)
    logger.debug("history_store | cleared %s/%s", email, agent_type or "all")
