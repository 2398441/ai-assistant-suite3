"""
Settings API
============
GET  /api/settings        — return current editable settings (keys masked)
POST /api/settings        — update settings in memory + persist to backend/.env
"""

import re
import os
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ...config.settings import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/settings", tags=["settings"])

# Fields exposed in the UI.  Sensitive = True means the value is masked on GET.
_FIELDS: list[dict] = [
    { "key": "anthropic_api_key",      "label": "Anthropic API Key",         "sensitive": True  },
    { "key": "model_name",             "label": "Model Name",                 "sensitive": False },
    { "key": "composio_api_key",       "label": "Composio API Key",           "sensitive": True  },
    { "key": "gmail_auth_config_id",   "label": "Gmail Auth Config ID",       "sensitive": True  },
    { "key": "calendar_auth_config_id","label": "Calendar Auth Config ID",    "sensitive": True  },
]

_ENV_PATH = Path(__file__).parents[4] / ".env"   # backend/.env


def _mask(value: str) -> str:
    """Show only the last 4 characters; mask the rest with •."""
    if not value:
        return ""
    visible = value[-4:]
    return f"{'•' * max(8, len(value) - 4)}{visible}"


def _read_env() -> dict[str, str]:
    """Parse backend/.env into a key→value dict (raw, unmasked)."""
    result: dict[str, str] = {}
    if not _ENV_PATH.exists():
        return result
    for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" in stripped:
            k, _, v = stripped.partition("=")
            result[k.strip()] = v.strip().strip('"').strip("'")
    return result


def _write_env(updates: dict[str, str]) -> None:
    """Update specific keys in backend/.env, preserving all other content."""
    if not _ENV_PATH.exists():
        raise HTTPException(status_code=500, detail=f".env not found at {_ENV_PATH}")

    lines = _ENV_PATH.read_text(encoding="utf-8").splitlines(keepends=True)
    written: set[str] = set()
    new_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            k = stripped.split("=", 1)[0].strip().upper()
            if k in {u.upper() for u in updates}:
                # Find the matching update key (case-insensitive)
                match = next(u for u in updates if u.upper() == k)
                new_lines.append(f"{k}={updates[match]}\n")
                written.add(match)
                continue
        new_lines.append(line if line.endswith("\n") else line + "\n" if line else line)

    # Append any keys that weren't already in the file
    for key, value in updates.items():
        if key not in written:
            new_lines.append(f"{key.upper()}={value}\n")

    _ENV_PATH.write_text("".join(new_lines), encoding="utf-8")


# ── Schemas ───────────────────────────────────────────────────────────────────

class SettingItem(BaseModel):
    key: str
    label: str
    sensitive: bool
    value: str          # masked on GET for sensitive fields

class SettingsResponse(BaseModel):
    settings: list[SettingItem]

class SettingsUpdateRequest(BaseModel):
    updates: dict[str, str]   # key → new raw value (empty string = no change)


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("", response_model=SettingsResponse)
async def get_settings():
    """Return current settings values. Sensitive fields are masked."""
    items: list[SettingItem] = []
    for f in _FIELDS:
        raw = str(getattr(settings, f["key"], "") or "")
        items.append(SettingItem(
            key=f["key"],
            label=f["label"],
            sensitive=f["sensitive"],
            value=_mask(raw) if f["sensitive"] else raw,
        ))
    return SettingsResponse(settings=items)


@router.post("")
async def update_settings(body: SettingsUpdateRequest):
    """
    Update settings. Empty or unchanged values are skipped.
    Changes are applied to the in-memory settings object immediately
    and persisted to backend/.env for survival across restarts.
    """
    valid_keys = {f["key"] for f in _FIELDS}
    filtered = {k: v for k, v in body.updates.items() if k in valid_keys and v.strip()}

    if not filtered:
        return {"status": "ok", "updated": []}

    # Check: skip values that look like a masked placeholder (all bullets)
    real_updates = {k: v for k, v in filtered.items() if not re.fullmatch(r"[•\*]+[A-Za-z0-9]{0,4}", v)}

    if not real_updates:
        return {"status": "ok", "updated": []}

    # 1. Update in-memory settings immediately
    for key, value in real_updates.items():
        setattr(settings, key, value)
        logger.info("Settings | updated %s in memory", key)

    # 2. Persist to .env
    try:
        _write_env(real_updates)
        logger.info("Settings | persisted %d key(s) to %s", len(real_updates), _ENV_PATH)
    except Exception as exc:
        logger.error("Settings | failed to write .env: %s", exc)
        raise HTTPException(status_code=500, detail=f"In-memory update succeeded but .env write failed: {exc}")

    return {"status": "ok", "updated": list(real_updates.keys())}
