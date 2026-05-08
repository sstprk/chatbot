"""
Slack channel history ingestor.

Pulls messages from configured Slack channels, cleans them,
and upserts into Qdrant with rich metadata.
"""

import json
import logging
import re
import time
from pathlib import Path

from slack_sdk.web.async_client import AsyncWebClient

from app.config import settings
from app.rag.qdrant_store import upsert_documents

logger = logging.getLogger(__name__)

SYNC_STATE_PATH = Path("data/sync_state.json")
MAX_CHUNK_LENGTH = 1500  # characters


def _load_sync_state() -> dict:
    """Load the sync state from disk."""
    if SYNC_STATE_PATH.exists():
        return json.loads(SYNC_STATE_PATH.read_text())
    return {}


def _save_sync_state(state: dict) -> None:
    """Persist sync state to disk."""
    SYNC_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    SYNC_STATE_PATH.write_text(json.dumps(state, indent=2))


def _clean_message_text(text: str, users_cache: dict[str, str]) -> str:
    """Replace Slack user ID mentions (<@U123>) with display names."""

    def _replace_mention(match: re.Match) -> str:
        user_id = match.group(1)
        return f"@{users_cache.get(user_id, user_id)}"

    return re.sub(r"<@(\w+)>", _replace_mention, text)


def _chunk_text(text: str, max_length: int = MAX_CHUNK_LENGTH) -> list[str]:
    """Split long text into chunks, preferring sentence boundaries."""
    if len(text) <= max_length:
        return [text]

    chunks: list[str] = []
    while text:
        if len(text) <= max_length:
            chunks.append(text)
            break

        # Try to split at sentence boundary
        split_at = text.rfind(". ", 0, max_length)
        if split_at == -1 or split_at < max_length // 2:
            split_at = text.rfind(" ", 0, max_length)
        if split_at == -1:
            split_at = max_length

        chunks.append(text[: split_at + 1].strip())
        text = text[split_at + 1 :].strip()

    return [c for c in chunks if c]


async def _build_user_cache(client: AsyncWebClient) -> dict[str, str]:
    """Fetch Slack user list and build an ID → display name mapping."""
    cache: dict[str, str] = {}
    try:
        response = await client.users_list()
        for member in response.get("members", []):
            uid = member.get("id", "")
            name = (
                member.get("profile", {}).get("display_name")
                or member.get("real_name")
                or member.get("name", uid)
            )
            cache[uid] = name
    except Exception:
        logger.warning("Failed to fetch Slack user list for name resolution", exc_info=True)
    return cache


async def _resolve_channel_id(client: AsyncWebClient, channel_name: str) -> str | None:
    """Look up a channel ID by name."""
    try:
        cursor = None
        while True:
            kwargs: dict = {"types": "public_channel,private_channel", "limit": 200}
            if cursor:
                kwargs["cursor"] = cursor
            response = await client.conversations_list(**kwargs)
            for ch in response.get("channels", []):
                if ch.get("name") == channel_name:
                    return ch["id"]
            cursor = response.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break
    except Exception:
        logger.error("Failed to resolve channel '%s'", channel_name, exc_info=True)
    return None


async def ingest_slack() -> int:
    """
    Ingest new messages from all configured Slack channels.

    Returns:
        Total number of documents upserted.
    """
    channels = settings.slack_channels_list
    if not channels:
        logger.info("No Slack channels configured for ingestion — skipping")
        return 0

    client = AsyncWebClient(token=settings.slack_bot_token)
    users_cache = await _build_user_cache(client)
    state = _load_sync_state()
    total_upserted = 0

    for channel_name in channels:
        try:
            channel_id = await _resolve_channel_id(client, channel_name)
            if not channel_id:
                logger.warning("Could not find channel '%s' — skipping", channel_name)
                continue

            state_key = f"slack:{channel_name}"
            oldest = state.get(state_key, "0")
            latest_ts = oldest

            # Paginate through channel history
            cursor = None
            documents: list[tuple[str, str, dict]] = []

            while True:
                kwargs: dict = {
                    "channel": channel_id,
                    "oldest": oldest,
                    "limit": 200,
                    "inclusive": False,
                }
                if cursor:
                    kwargs["cursor"] = cursor

                response = await client.conversations_history(**kwargs)
                messages = response.get("messages", [])

                for msg in messages:
                    # Skip bot messages and system messages
                    if msg.get("subtype") or msg.get("bot_id"):
                        continue

                    text = msg.get("text", "").strip()
                    if not text:
                        continue

                    ts = msg.get("ts", "")
                    user_id = msg.get("user", "unknown")
                    author = users_cache.get(user_id, user_id)

                    # Fetch thread replies if present
                    thread_ts = msg.get("thread_ts")
                    if thread_ts and thread_ts == ts:
                        try:
                            thread_resp = await client.conversations_replies(
                                channel=channel_id,
                                ts=thread_ts,
                                limit=100,
                            )
                            thread_messages = thread_resp.get("messages", [])[1:]  # skip parent
                            for reply in thread_messages:
                                reply_text = reply.get("text", "").strip()
                                if reply_text:
                                    reply_author = users_cache.get(
                                        reply.get("user", ""), "unknown"
                                    )
                                    text += f"\n[{reply_author}]: {reply_text}"
                        except Exception:
                            logger.warning(
                                "Failed to fetch thread replies for ts=%s", thread_ts, exc_info=True
                            )

                    # Clean and chunk
                    text = _clean_message_text(text, users_cache)
                    chunks = _chunk_text(text)

                    for i, chunk in enumerate(chunks):
                        doc_id = f"slack-{channel_name}-{ts}-{i}"
                        metadata = {
                            "source": "slack",
                            "channel": channel_name,
                            "ts": ts,
                            "author": author,
                        }
                        documents.append((doc_id, chunk, metadata))

                    if float(ts) > float(latest_ts):
                        latest_ts = ts

                cursor = response.get("response_metadata", {}).get("next_cursor")
                if not cursor:
                    break

            # Batch upsert
            if documents:
                upserted = await upsert_documents(documents)
                total_upserted += upserted
                logger.info(
                    "Ingested %d chunks from Slack channel #%s",
                    upserted,
                    channel_name,
                )

            # Update sync state
            state[state_key] = latest_ts
            _save_sync_state(state)

        except Exception:
            logger.error(
                "Error ingesting Slack channel '%s'",
                channel_name,
                exc_info=True,
            )

    return total_upserted
