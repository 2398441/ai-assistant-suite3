from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from ...core.session_store import session_store
from ...core.agent import stream_agent_response
from ...core.token_store import validate_token
from ...core.history_store import clear_history
from ...models.schemas import (
    ChatMessageRequest,
    ClearMessagesRequest,
    ClearMessagesResponse,
)

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _require_token(email: str, token: str | None) -> None:
    if not validate_token(email, token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session. Please sign in again.",
        )


@router.post("/message")
async def chat_message(request: ChatMessageRequest):
    """
    Send a message and receive a streaming SSE response.

    agent_type: "workspace" | "gmail" | "calendar"
    "workspace" (default) — full Gmail + Calendar + Contacts access in one session.

    SSE event shapes:
      {"type": "text",       "content": "<delta>"}
      {"type": "tool_start", "name": "<action>", "display": "<label>"}
      {"type": "tool_end",   "name": "<action>", "success": true|false}
      {"type": "done"}
      {"type": "error",      "message": "<msg>"}
    """
    _require_token(request.email, request.session_token)

    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    session = session_store.get(request.email)
    if not session or not session.is_connected:
        raise HTTPException(
            status_code=403,
            detail="Google account not connected. Please sign in first.",
        )

    msg = request.message.strip()
    agent_type = request.agent_type

    if agent_type in ("gmail", "calendar", "workspace"):
        stream = stream_agent_response(session, msg, agent_type)
    else:
        stream = stream_agent_response(session, msg, "workspace")

    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/clear", response_model=ClearMessagesResponse)
async def clear_messages(request: ClearMessagesRequest):
    """
    Clear conversation history for a user (in-memory + persisted store).
    Clears the specified agent's history, or all agents if agent_type is omitted.
    """
    _require_token(request.email, request.session_token)
    session_store.clear_messages(request.email, request.agent_type)
    clear_history(request.email, request.agent_type)
    return ClearMessagesResponse(ok=True)
