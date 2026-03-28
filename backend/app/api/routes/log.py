"""
Client-side error receiver.

Accepts error payloads POSTed from the browser (window.onerror,
unhandledrejection) and appends them to the unified app log file.

To disable runtime error capture from the browser:
  1. In main.py — comment out: from .routes.log import router as log_router
  2. In main.py — comment out: app.include_router(log_router)
  3. In frontend/app/layout.tsx — comment out the "Runtime error capture" useEffect block
  This file and the /api/log/error endpoint can remain; they just won't be called.
"""

import os
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/log", tags=["log"])

# ── Log file path — mirrors the path used in restart.sh ───────────────────────
_PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..")
)
_LOG_FILE = os.path.join(_PROJECT_ROOT, "logs", "app.log")


class ClientErrorPayload(BaseModel):
    """Shape of the error payload sent by the browser."""
    source: str = "FRONTEND"   # always "FRONTEND" from the browser
    context: str = ""          # e.g. "window.onerror", "unhandledrejection"
    message: str               # the error message string


def _write_log(level: str, source: str, message: str) -> None:
    """Append a single formatted line to the unified log file."""
    os.makedirs(os.path.dirname(_LOG_FILE), exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{timestamp:<19} | {level:<7} | {source:<8} | {message}\n"
    with open(_LOG_FILE, "a") as f:
        f.write(line)


@router.post("/error", status_code=204)
async def receive_client_error(payload: ClientErrorPayload) -> None:
    """
    Receive a client-side (browser) error and write it to the unified log.
    Returns 204 No Content — the browser does not need a response body.
    """
    context_prefix = f"[{payload.context}] " if payload.context else ""
    _write_log("ERROR", "CLIENT", f"{context_prefix}{payload.message}")
