import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slack_bolt.adapter.starlette.async_handler import AsyncSlackRequestHandler

from app.bot import build_bolt_app, set_client
from app.client import MnemoClient
from app.config import settings

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "Starting %s Slack Bot: mnemo=%s ollama=%s model=%s",
        settings.bot_name,
        settings.container_url,
        settings.ollama_url,
        settings.ollama_model,
    )

    bolt_app = build_bolt_app()

    mnemo_client = MnemoClient(
        base_url=settings.container_url,
        api_key=settings.user_api_key,
        timeout=settings.query_timeout,
    )
    set_client(mnemo_client)

    reachable = await mnemo_client.health()
    if reachable:
        logger.info("user_container_reachable url=%s", settings.container_url)
    else:
        logger.warning(
            "user_container_unreachable url=%s — bot will start anyway",
            settings.container_url,
        )

    app.state.bolt = bolt_app
    app.state.handler = AsyncSlackRequestHandler(bolt_app)
    app.state.mnemo_client = mnemo_client

    logger.info(
        "%s Slack Bot ready: port=%d",
        settings.bot_name,
        settings.app_port,
    )
    yield

    await mnemo_client.close()
    logger.info("%s Slack Bot shut down", settings.bot_name)


app = FastAPI(
    title="Mnemo Slack Bot",
    description=(
        "Slack chatbot that uses Mnemo for retrieval and a local Ollama LLM "
        "for answer generation. Mnemo returns document chunks; this service "
        "turns them into human-readable answers."
    ),
    version="0.2.0",
    lifespan=lifespan,
)


@app.post("/slack/events")
async def slack_events(request: Request):
    """Handle incoming Slack events (mentions, DMs, URL verification)."""
    return await request.app.state.handler.handle(request)


@app.post("/slack/interactions")
async def slack_interactions(request: Request):
    """Handle Slack interactive components (buttons, modals)."""
    return await request.app.state.handler.handle(request)


@app.get("/health")
async def health(request: Request):
    """Liveness check. Reports user container reachability."""
    reachable = await request.app.state.mnemo_client.health()
    return {
        "status": "ok",
        "container_url": settings.container_url,
        "container_reachable": reachable,
        "ollama_url": settings.ollama_url,
        "ollama_model": settings.ollama_model,
        "bot_name": settings.bot_name,
    }


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )
