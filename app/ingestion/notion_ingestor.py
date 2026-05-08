"""
Notion page ingestor.

Uses LlamaIndex NotionPageReader to load pages, chunks them with
SentenceSplitter, and upserts into Qdrant.
"""

import json
import logging
from pathlib import Path

from llama_index.core.node_parser import SentenceSplitter
from llama_index.readers.notion import NotionPageReader

from app.config import settings
from app.rag.qdrant_store import upsert_documents

logger = logging.getLogger(__name__)

SYNC_STATE_PATH = Path("data/sync_state.json")

# Chunking parameters
CHUNK_SIZE = 512
CHUNK_OVERLAP = 64


def _load_sync_state() -> dict:
    """Load the sync state from disk."""
    if SYNC_STATE_PATH.exists():
        return json.loads(SYNC_STATE_PATH.read_text())
    return {}


def _save_sync_state(state: dict) -> None:
    """Persist sync state to disk."""
    SYNC_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    SYNC_STATE_PATH.write_text(json.dumps(state, indent=2))


async def ingest_notion() -> int:
    """
    Ingest pages from Notion and upsert into Qdrant.

    Returns:
        Total number of document chunks upserted.
    """
    page_ids = settings.notion_page_ids_list
    if not page_ids:
        logger.info("No Notion page IDs configured for ingestion — skipping")
        return 0

    if not settings.notion_integration_token:
        logger.warning("NOTION_INTEGRATION_TOKEN not set — skipping Notion ingestion")
        return 0

    reader = NotionPageReader(integration_token=settings.notion_integration_token)
    splitter = SentenceSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    state = _load_sync_state()
    total_upserted = 0

    for page_id in page_ids:
        try:
            state_key = f"notion:{page_id}"

            # Load the Notion page
            logger.info("Loading Notion page %s...", page_id)
            documents = reader.load_data(page_ids=[page_id])

            if not documents:
                logger.warning("No content returned for Notion page %s", page_id)
                continue

            # Extract title from the first document's metadata
            title = "Untitled"
            if documents and documents[0].metadata:
                title = documents[0].metadata.get("title", "Untitled")

            # Chunk the document content
            all_chunks: list[tuple[str, str, dict]] = []

            for doc in documents:
                text = doc.get_content()
                if not text.strip():
                    continue

                # Use SentenceSplitter to create nodes
                nodes = splitter.get_nodes_from_documents([doc])

                for i, node in enumerate(nodes):
                    chunk_text = node.get_content()
                    if not chunk_text.strip():
                        continue

                    doc_id = f"notion-{page_id}-{i}"
                    metadata = {
                        "source": "notion",
                        "page_id": page_id,
                        "title": title,
                        "chunk_index": i,
                    }
                    all_chunks.append((doc_id, chunk_text, metadata))

            # Batch upsert
            if all_chunks:
                upserted = await upsert_documents(all_chunks)
                total_upserted += upserted
                logger.info(
                    "Ingested %d chunks from Notion page '%s' (%s)",
                    upserted,
                    title,
                    page_id,
                )

            # Update sync state
            from datetime import datetime, timezone

            state[state_key] = datetime.now(timezone.utc).isoformat()
            _save_sync_state(state)

        except Exception:
            logger.error(
                "Error ingesting Notion page '%s'",
                page_id,
                exc_info=True,
            )

    return total_upserted
