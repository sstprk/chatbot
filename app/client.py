from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


class BelleqClient:

    def __init__(self, base_url: str, api_key: str = "", timeout: float = 120.0):
        self._url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._client = httpx.AsyncClient(timeout=self._timeout)

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            h["X-Api-Key"] = self._api_key
        return h

    async def query(
        self,
        text: str,
        include_provenance: bool = False,
    ) -> dict:
        """
        POST {container_url}/query
        Sends plain text query to Belleq user container.
        Returns dict with "chunks" list and optional "provenance".
        On any error returns {"error": str, "chunks": []}
        Never raises.
        """
        body = {
            "query": text,
            "include_provenance": include_provenance,
        }
        try:
            r = await self._client.post(
                f"{self._url}/query",
                headers=self._headers(),
                json=body,
            )
            r.raise_for_status()
            return r.json()
        except httpx.TimeoutException:
            logger.error("belleq_query_timeout url=%s", self._url)
            return {"error": "timeout", "chunks": []}
        except httpx.HTTPStatusError as e:
            logger.error(
                "belleq_query_http_error status=%d", e.response.status_code
            )
            return {"error": f"http_{e.response.status_code}", "chunks": []}
        except Exception as e:
            logger.error("belleq_query_error error=%s", e)
            return {"error": str(e), "chunks": []}

    async def health(self) -> bool:
        try:
            r = await self._client.get(
                f"{self._url}/query/health",
                timeout=5.0,
            )
            return r.status_code == 200
        except Exception:
            return False

    async def close(self) -> None:
        await self._client.aclose()


async def generate_answer(
    chunks: list[dict],
    query: str,
    settings,
) -> str:
    """
    Build a prompt from retrieved chunks and call Ollama to generate
    an answer. This is the chatbot's own LLM — not part of Belleq.

    Returns the generated answer string.
    On error returns settings.error_message.
    """
    if not chunks:
        return (
            "I couldn't find any relevant information in the "
            "knowledge base for your question."
        )

    # Build numbered context block from chunks
    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        source = chunk.get("source", "unknown")
        channel = chunk.get("channel", "")
        title = chunk.get("doc_title", "")
        label = f"#{channel}" if channel else title or source
        context_parts.append(
            f"[{i}] Source: {label}\n{chunk.get('text', '')}"
        )
    context = "\n\n".join(context_parts)

    prompt = (
        f"{settings.system_prompt}\n\n"
        f"── Retrieved Context ──\n{context}\n\n"
        f"── Question ──\n{query}\n\n"
        f"Answer:"
    )

    try:
        async with httpx.AsyncClient(timeout=settings.llm_timeout) as client:
            r = await client.post(
                f"{settings.ollama_url}/api/generate",
                json={
                    "model": settings.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": settings.llm_temperature,
                        "num_predict": settings.llm_max_tokens,
                    },
                },
            )
            r.raise_for_status()
            return r.json().get("response", "").strip()
    except httpx.TimeoutException:
        logger.error("ollama_timeout url=%s", settings.ollama_url)
        return settings.error_message
    except Exception as e:
        logger.error("ollama_error error=%s", e)
        return settings.error_message


def format_sources(chunks: list[dict], settings) -> str:
    """
    Build a Slack mrkdwn source citation block from chunks.
    Deduplicates by source key. Max 5 sources.
    Returns empty string if show_sources=False or no chunks.
    """
    if not settings.show_sources or not chunks:
        return ""

    seen: set[str] = set()
    lines: list[str] = []
    for chunk in chunks:
        source = chunk.get("source", "unknown")
        channel = chunk.get("channel", "")
        title = chunk.get("doc_title", "")
        if source == "slack" and channel:
            key = f"slack:#{channel}"
            label = f"Slack › #{channel}"
        elif source == "notion" and title:
            key = f"notion:{title}"
            label = f"Notion › {title}"
        else:
            key = f"{source}:{title or 'unknown'}"
            label = f"{source.capitalize()} › {title or 'unknown'}"
        if key not in seen:
            seen.add(key)
            lines.append(f"• {label}")
        if len(lines) >= 5:
            break

    if not lines:
        return ""
    return "\n📚 *Sources:*\n" + "\n".join(lines)
