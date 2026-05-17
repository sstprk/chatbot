from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from slack_bolt.async_app import AsyncApp

from app.client import BelleqClient, format_sources, generate_answer
from app.config import settings

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_client: BelleqClient | None = None


def set_client(client: BelleqClient) -> None:
    global _client
    _client = client


def _clean_query(text: str) -> str:
    return re.sub(r"<@\w+>", "", text).strip()


def _is_bot_message(event: dict) -> bool:
    return bool(event.get("bot_id") or event.get("subtype") == "bot_message")


def build_bolt_app() -> AsyncApp:
    bolt = AsyncApp(
        token=settings.slack_bot_token,
        signing_secret=settings.slack_signing_secret,
    )

    @bolt.event("app_mention")
    async def handle_mention(event, say, client):
        if _is_bot_message(event):
            return

        user = event.get("user", "")
        text = event.get("text", "")
        ts = event.get("ts", "")
        thread_ts = event.get("thread_ts", ts)
        query = _clean_query(text)

        if not query:
            await say(
                text=f"Hi <@{user}>! Ask me anything about the company knowledge base.",
                thread_ts=thread_ts,
            )
            return

        try:
            await client.reactions_add(
                channel=event["channel"],
                timestamp=ts,
                name=settings.typing_emoji,
            )
        except Exception:
            pass

        result = await _client.query(
            text=query,
            include_provenance=settings.show_provenance,
        )

        if result.get("error"):
            answer = settings.error_message
        else:
            chunks = result.get("chunks", [])
            answer = await generate_answer(chunks, query, settings)
            sources = format_sources(chunks, settings)
            answer = answer + sources

            if settings.show_provenance and result.get("provenance"):
                prov = result["provenance"]
                answer += (
                    f"\n\n📊 _{prov.get('cache_hits', 0)} cached · "
                    f"{prov.get('global_hits', 0)} from knowledge base_"
                )

        try:
            await client.reactions_remove(
                channel=event["channel"],
                timestamp=ts,
                name=settings.typing_emoji,
            )
        except Exception:
            pass

        await say(
            text=f"<@{user}> {answer}",
            thread_ts=thread_ts,
        )

    @bolt.event("message")
    async def handle_message(event, say):
        if event.get("channel_type") != "im":
            return
        if _is_bot_message(event):
            return
        if event.get("subtype"):
            return

        query = event.get("text", "").strip()
        if not query:
            return

        await say(f":{settings.typing_emoji}: Thinking...")

        result = await _client.query(
            text=query,
            include_provenance=settings.show_provenance,
        )

        if result.get("error"):
            answer = settings.error_message
        else:
            chunks = result.get("chunks", [])
            answer = await generate_answer(chunks, query, settings)
            sources = format_sources(chunks, settings)
            answer = answer + sources

            if settings.show_provenance and result.get("provenance"):
                prov = result["provenance"]
                answer += (
                    f"\n\n📊 _{prov.get('cache_hits', 0)} cached · "
                    f"{prov.get('global_hits', 0)} from knowledge base_"
                )

        await say(answer)

    @bolt.event("app_home_opened")
    async def handle_app_home(event, client):
        user_id = event["user"]
        await client.views_publish(
            user_id=user_id,
            view={
                "type": "home",
                "blocks": [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": f"Welcome to {settings.bot_name}",
                        },
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": (
                                "*How to use:*\n"
                                f"• Mention me in any channel: `@{settings.bot_name} your question`\n"
                                "• Send me a direct message with your question\n\n"
                                "I'll search the company knowledge base and answer based "
                                "on what I find."
                            ),
                        },
                    },
                ],
            },
        )

    @bolt.error
    async def handle_error(error, body, logger):
        logger.error("bolt_error error=%s body=%s", error, body)

    return bolt
