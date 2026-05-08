"""
Embedding helper — calls the Ollama /api/embed endpoint directly via httpx.
Uses nomic-embed-text (768-dimensional vectors).
"""

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    """Lazy-init a shared async HTTP client."""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=120.0)
    return _client


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    Embed one or more texts using Ollama's /api/embed endpoint.

    Args:
        texts: List of strings to embed.

    Returns:
        List of embedding vectors (each a list of floats).
    """
    if not texts:
        return []

    client = _get_client()
    url = f"{settings.ollama_base_url}/api/embed"

    try:
        response = await client.post(
            url,
            json={
                "model": settings.ollama_embed_model,
                "input": texts,
            },
        )
        response.raise_for_status()
        data = response.json()
        embeddings = data.get("embeddings", [])
        logger.debug("Embedded %d texts → %d vectors", len(texts), len(embeddings))
        return embeddings
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Ollama embed request failed: %s — %s",
            exc.response.status_code,
            exc.response.text,
        )
        raise
    except httpx.RequestError as exc:
        logger.error("Ollama embed request error: %s", exc)
        raise


async def embed_query(text: str) -> list[float]:
    """Convenience wrapper: embed a single text and return its vector."""
    vectors = await embed_texts([text])
    return vectors[0]
