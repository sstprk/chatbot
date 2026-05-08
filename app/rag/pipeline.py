"""
RAG pipeline — query → retrieve → generate.

Embeds the user query, searches Qdrant for relevant context, builds a
prompt with source citations, and calls Ollama to generate a response.
"""

import logging
from datetime import datetime, timezone

import httpx

from app.config import settings
from app.rag.qdrant_store import SearchResult, search

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a helpful internal company assistant. Your role is to answer \
questions using the retrieved knowledge from company Slack channels and Notion pages.

Rules:
- Answer ONLY based on the provided context. If the context does not contain \
enough information, say so honestly.
- Be concise and professional.
- When referencing information, mention the source (channel name, page title, etc.).
- Format your responses clearly with bullet points or numbered lists when appropriate.
"""

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    """Lazy-init a shared async HTTP client."""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=180.0)
    return _client


def _build_context(results: list[SearchResult]) -> str:
    """Format search results into a numbered context block."""
    if not results:
        return "(No relevant context found.)"

    parts: list[str] = []
    for i, result in enumerate(results, 1):
        source = result.metadata.get("source", "unknown")
        meta_parts: list[str] = [f"source={source}"]

        if source == "slack":
            channel = result.metadata.get("channel", "?")
            author = result.metadata.get("author", "?")
            ts = result.metadata.get("ts", "")
            meta_parts.append(f"channel=#{channel}")
            meta_parts.append(f"author={author}")
            if ts:
                try:
                    dt = datetime.fromtimestamp(float(ts), tz=timezone.utc)
                    meta_parts.append(f"date={dt.strftime('%Y-%m-%d %H:%M UTC')}")
                except (ValueError, OSError):
                    pass
        elif source == "notion":
            title = result.metadata.get("title", "Untitled")
            meta_parts.append(f"page={title}")

        header = " | ".join(meta_parts)
        parts.append(f"[{i}] ({header})\n{result.text}")

    return "\n\n".join(parts)


def _format_sources(results: list[SearchResult]) -> str:
    """Build a compact Slack-mrkdwn source citation block."""
    if not results:
        return ""

    seen: set[str] = set()
    lines: list[str] = []
    for result in results:
        source = result.metadata.get("source", "unknown")
        if source == "slack":
            key = f"slack:#{result.metadata.get('channel', '?')}"
            label = f"Slack › #{result.metadata.get('channel', '?')}"
        elif source == "notion":
            key = f"notion:{result.metadata.get('page_id', '?')}"
            label = f"Notion › {result.metadata.get('title', 'Untitled')}"
        else:
            key = f"other:{result.text[:30]}"
            label = "Other source"

        if key not in seen:
            seen.add(key)
            lines.append(f"• {label}")

    return "\n".join(lines)


async def query(user_message: str, top_k: int = 5) -> str:
    """
    Run the full RAG pipeline: embed → retrieve → generate.

    Args:
        user_message: The user's natural-language question.
        top_k: Number of context chunks to retrieve.

    Returns:
        Generated answer string with source citations appended.
    """
    # 1. Retrieve relevant context from Qdrant
    results = await search(user_message, top_k=top_k)
    context = _build_context(results)

    # 2. Build the full prompt
    prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"── Retrieved Context ──\n{context}\n\n"
        f"── User Question ──\n{user_message}\n\n"
        f"Answer:"
    )

    # 3. Call Ollama /api/generate
    client = _get_client()
    url = f"{settings.ollama_base_url}/api/generate"

    try:
        response = await client.post(
            url,
            json={
                "model": settings.ollama_model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.3,
                    "num_predict": 1024,
                },
            },
        )
        response.raise_for_status()
        data = response.json()
        answer = data.get("response", "").strip()
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Ollama generate failed: %s — %s",
            exc.response.status_code,
            exc.response.text,
        )
        return "⚠️ Sorry, I couldn't generate a response right now. Please try again later."
    except httpx.RequestError as exc:
        logger.error("Ollama generate request error: %s", exc)
        return "⚠️ Sorry, I couldn't reach the language model. Please try again later."

    # 4. Append source citations
    sources = _format_sources(results)
    if sources:
        answer += f"\n\n📚 *Sources:*\n{sources}"

    return answer
