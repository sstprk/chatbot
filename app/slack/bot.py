"""
Slack Bolt app — HTTP mode.

Creates the Bolt app with event handlers and exposes it
as an ASGI application for mounting inside FastAPI.
"""

import logging

from slack_bolt.adapter.starlette.async_handler import AsyncSlackRequestHandler
from slack_bolt.async_app import AsyncApp

from app.config import settings
from app.slack.handlers import register_handlers

logger = logging.getLogger(__name__)

# Initialise the Slack Bolt app in HTTP mode (socket_mode=False is the default)
bolt_app = AsyncApp(
    token=settings.slack_bot_token,
    signing_secret=settings.slack_signing_secret,
)

# Register event handlers
register_handlers(bolt_app)

# ASGI handler for Starlette / FastAPI mounting
slack_handler = AsyncSlackRequestHandler(bolt_app)
