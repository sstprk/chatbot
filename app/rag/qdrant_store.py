"""
Qdrant vector store helpers — collection management, upsert, and search.
"""

import logging
import uuid
from dataclasses import dataclass

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    PointStruct,
    VectorParams,
)

from app.config import settings
from app.rag.embeddings import embed_query, embed_texts

logger = logging.getLogger(__name__)

# nomic-embed-text produces 768-dimensional vectors
VECTOR_SIZE = 768

_qdrant_client: AsyncQdrantClient | None = None


@dataclass
class SearchResult:
    """A single search result from Qdrant."""

    text: str
    score: float
    metadata: dict


async def get_qdrant_client() -> AsyncQdrantClient:
    """Return a (lazily initialised) async Qdrant client."""
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = AsyncQdrantClient(url=settings.qdrant_url)
    return _qdrant_client


async def ensure_collection() -> None:
    """Create the Qdrant collection if it does not exist."""
    client = await get_qdrant_client()
    collections = await client.get_collections()
    existing_names = {c.name for c in collections.collections}

    if settings.qdrant_collection not in existing_names:
        await client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=VectorParams(
                size=VECTOR_SIZE,
                distance=Distance.COSINE,
            ),
        )
        logger.info(
            "Created Qdrant collection '%s' (dim=%d, cosine)",
            settings.qdrant_collection,
            VECTOR_SIZE,
        )
    else:
        logger.debug("Qdrant collection '%s' already exists", settings.qdrant_collection)


async def upsert_documents(
    documents: list[tuple[str, str, dict]],
) -> int:
    """
    Embed and upsert documents into Qdrant.

    Args:
        documents: List of (id, text, metadata) tuples.
                   If id is empty, a UUID4 is generated.

    Returns:
        Number of points upserted.
    """
    if not documents:
        return 0

    ids = [doc[0] or str(uuid.uuid4()) for doc in documents]
    texts = [doc[1] for doc in documents]
    metadatas = [doc[2] for doc in documents]

    # Embed all texts in one batch
    vectors = await embed_texts(texts)

    if len(vectors) != len(texts):
        logger.error(
            "Embedding count mismatch: expected %d, got %d",
            len(texts),
            len(vectors),
        )
        raise ValueError("Embedding count mismatch")

    points = [
        PointStruct(
            id=point_id,
            vector=vector,
            payload={"text": text, **metadata},
        )
        for point_id, vector, text, metadata in zip(ids, vectors, texts, metadatas)
    ]

    client = await get_qdrant_client()
    await client.upsert(
        collection_name=settings.qdrant_collection,
        points=points,
    )

    logger.info("Upserted %d points into '%s'", len(points), settings.qdrant_collection)
    return len(points)


async def search(query: str, top_k: int = 5) -> list[SearchResult]:
    """
    Embed a query and search Qdrant for the top-k most similar documents.

    Args:
        query: Natural-language search query.
        top_k: Number of results to return.

    Returns:
        List of SearchResult objects sorted by relevance (descending).
    """
    query_vector = await embed_query(query)
    client = await get_qdrant_client()

    hits = await client.query_points(
        collection_name=settings.qdrant_collection,
        query=query_vector,
        limit=top_k,
        with_payload=True,
    )

    results: list[SearchResult] = []
    for hit in hits.points:
        payload = hit.payload or {}
        text = payload.pop("text", "")
        results.append(
            SearchResult(
                text=text,
                score=hit.score,
                metadata=payload,
            )
        )

    logger.debug("Search for '%s' returned %d results", query[:60], len(results))
    return results
