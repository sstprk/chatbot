"""
Slack event handlers — processes @mentions and DMs through the RAG pipeline.
"""

import logging
import re

from slack_bolt.async_app import AsyncApp

from app.rag import pipeline

logger = logging.getLogger(__name__)


def _strip_bot_mention(text: str) -> str:
    """Remove the bot @mention from the beginning of a message."""
    return re.sub(r"^\s*<@\w+>\s*", "", text).strip()


def register_handlers(app: AsyncApp) -> None:
    """Register all Slack event handlers on the Bolt app."""

    @app.event("app_mention")
    async def handle_app_mention(event: dict, say, client) -> None:
        """Handle @bot mentions in channels."""
        channel = event.get("channel", "")
        thread_ts = event.get("thread_ts") or event.get("ts", "")
        user_message = _strip_bot_mention(event.get("text", ""))
        ts = event.get("ts", "")

        if not user_message:
            await say(
                text="Hey! Ask me a question and I'll search our knowledge base. 🔍",
                channel=channel,
                thread_ts=thread_ts,
            )
            return

        # Add a "thinking" reaction while processing
        try:
            await client.reactions_add(
                channel=channel,
                name="hourglass_flowing_sand",
                timestamp=ts,
            )
        except Exception:
            logger.debug("Could not add thinking reaction", exc_info=True)

        try:
            answer = await pipeline.query(user_message)
            await say(text=answer, channel=channel, thread_ts=thread_ts)
        except Exception:
            logger.error("Error processing app_mention", exc_info=True)
            await say(
                text="⚠️ Sorry, something went wrong while processing your question. Please try again.",
                channel=channel,
                thread_ts=thread_ts,
            )
        finally:
            # Remove the "thinking" reaction
            try:
                await client.reactions_remove(
                    channel=channel,
                    name="hourglass_flowing_sand",
                    timestamp=ts,
                )
            except Exception:
                pass

    @app.event("message")
    async def handle_direct_message(event: dict, say, client) -> None:
        """Handle direct messages to the bot."""
        # Only process DMs (channel_type == "im"), skip bot messages
        if event.get("channel_type") != "im":
            return
        if event.get("bot_id") or event.get("subtype"):
            return

        user_message = event.get("text", "").strip()
        channel = event.get("channel", "")
        ts = event.get("ts", "")

        if not user_message:
            return

        # Add a "thinking" reaction while processing
        try:
            await client.reactions_add(
                channel=channel,
                name="hourglass_flowing_sand",
                timestamp=ts,
            )
        except Exception:
            logger.debug("Could not add thinking reaction", exc_info=True)

        try:
            answer = await pipeline.query(user_message)
            await say(text=answer, channel=channel)
        except Exception:
            logger.error("Error processing direct message", exc_info=True)
            await say(
                text="⚠️ Sorry, something went wrong while processing your question. Please try again.",
                channel=channel,
            )
        finally:
            try:
                await client.reactions_remove(
                    channel=channel,
                    name="hourglass_flowing_sand",
                    timestamp=ts,
                )
            except Exception:
                pass
