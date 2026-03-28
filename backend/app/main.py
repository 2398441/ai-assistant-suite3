import truststore
truststore.inject_into_ssl()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config.settings import settings
from .api.routes import auth, chat, triggers, agents, notifications, settings as settings_route

# ── Client-side error logging ─────────────────────────────────────────────────
# Receives browser errors (window.onerror, unhandledrejection) and writes them
# to the unified log file.
# To disable: comment out the two lines below (import and include_router).
from .api.routes import log as log_route
# ── End client-side error logging ────────────────────────────────────────────

app = FastAPI(
    title="AI Assistant API",
    description="Claude-powered assistant with Gmail and Google Calendar integration",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(triggers.router)
app.include_router(agents.router)
app.include_router(notifications.router)
app.include_router(settings_route.router)

# ── Client-side error logging (disable by commenting out) ────────────────────
app.include_router(log_route.router)
# ── End client-side error logging ────────────────────────────────────────────


@app.get("/health")
async def health():
    return {"status": "ok"}
