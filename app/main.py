"""
FastAPI entrypoint.

- Mounts Slack Bolt at /slack/events
- Health check at /health
- Starts ingestion scheduler on startup
- Ensures Qdrant collection exists on startup
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import settings
from app.ingestion.scheduler import run_initial_ingestion, start_scheduler, stop_scheduler
from app.rag.qdrant_store import ensure_collection
from app.slack.bot import slack_handler

# ── Logging ──────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── Lifespan ─────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    logger.info("Starting Company Chatbot...")

    # Ensure Qdrant collection exists
    await ensure_collection()

    # Start the ingestion scheduler
    scheduler = start_scheduler()

    # Run initial ingestion in the background (don't block startup)
    asyncio.create_task(run_initial_ingestion())

    logger.info("Company Chatbot is ready ✓")
    yield

    # Shutdown
    stop_scheduler()
    logger.info("Company Chatbot shut down")


# ── FastAPI app ──────────────────────────────────────────────────────
app = FastAPI(
    title="Company Chatbot",
    description="Internal RAG-powered chatbot with Slack integration",
    version="1.0.0",
    lifespan=lifespan,
)


# ── Health check ─────────────────────────────────────────────────────
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "model": settings.ollama_model,
        "embed_model": settings.ollama_embed_model,
        "collection": settings.qdrant_collection,
    }


# ── Slack event endpoints ────────────────────────────────────────────
@app.post("/slack/events")
async def slack_events(request: Request):
    """Handle incoming Slack events (mentions, DMs, challenges)."""
    return await slack_handler.handle(request)


@app.post("/slack/interactions")
async def slack_interactions(request: Request):
    """Handle Slack interactive components (buttons, modals, etc.)."""
    return await slack_handler.handle(request)


# ── Global error handler ─────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch-all error handler to prevent 500s from leaking stack traces."""
    logger.error("Unhandled exception: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )
