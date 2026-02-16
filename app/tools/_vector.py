"""Vector search (ChromaDB + Ollama) init and tool handlers."""

import json
import logging

from .. import config as _config
from ..config import VectorSearchConfig

log = logging.getLogger(__name__)

_chroma_collection = None


def init_vector_search(config: VectorSearchConfig):
    """Initialize ChromaDB with Ollama embeddings. Call once at startup."""
    global _chroma_collection
    if not config.enabled:
        return
    try:
        import chromadb
        from chromadb.utils.embedding_functions import OllamaEmbeddingFunction

        db_path = _config.STATE_DIR / "vectordb"
        db_path.mkdir(parents=True, exist_ok=True)

        ef = OllamaEmbeddingFunction(
            model_name=config.model,
            url=f"{config.ollama_url.rstrip('/')}/api/embed",
        )
        client = chromadb.PersistentClient(path=str(db_path))
        _chroma_collection = client.get_or_create_collection(
            config.collection, embedding_function=ef
        )
        log.info(
            f"Vector search initialized: collection={config.collection}, "
            f"model={config.model}, entries={_chroma_collection.count()}"
        )
    except Exception:
        log.exception("Failed to initialize vector search")


def get_collection():
    """Return the current ChromaDB collection (or None if not initialized)."""
    return _chroma_collection


def handle_vector_save(arguments: dict) -> str:
    if _chroma_collection is None:
        return "Error: vector search not initialized."
    entry_id = arguments.get("id", "").strip()
    content = arguments.get("content", "").strip()
    if not entry_id:
        return "Error: id is required."
    if not content:
        return "Error: content is required."
    metadata = arguments.get("metadata") or {}
    try:
        _chroma_collection.upsert(
            ids=[entry_id], documents=[content], metadatas=[metadata]
        )
        return f"Saved entry '{entry_id}' to vector database."
    except Exception as e:
        return f"Error saving to vector database: {e}"


def handle_vector_search(arguments: dict) -> str:
    if _chroma_collection is None:
        return "Error: vector search not initialized."
    query = arguments.get("query", "").strip()
    if not query:
        return "Error: query is required."
    n = min(int(arguments.get("n", 5)), 20)
    try:
        if _chroma_collection.count() == 0:
            return "Vector database is empty."
        results = _chroma_collection.query(query_texts=[query], n_results=n)
        ids = results["ids"][0]
        docs = results["documents"][0]
        distances = (
            results["distances"][0] if results.get("distances") else [None] * len(ids)
        )
        metadatas = (
            results["metadatas"][0] if results.get("metadatas") else [{}] * len(ids)
        )
        if not ids:
            return f"No results found for: {query}"
        lines = []
        for i, (eid, doc, dist, meta) in enumerate(
            zip(ids, docs, distances, metadatas), 1
        ):
            parts = [
                f"**{i}. [{eid}]** (distance: {dist:.4f})"
                if dist is not None
                else f"**{i}. [{eid}]**"
            ]
            if meta:
                parts.append(f"  metadata: {json.dumps(meta)}")
            parts.append(f"  {doc}")
            lines.append("\n".join(parts))
        return "\n\n".join(lines)
    except Exception as e:
        return f"Error searching vector database: {e}"


def handle_vector_delete(arguments: dict) -> str:
    if _chroma_collection is None:
        return "Error: vector search not initialized."
    entry_id = arguments.get("id", "").strip()
    if not entry_id:
        return "Error: id is required."
    try:
        _chroma_collection.delete(ids=[entry_id])
        return f"Deleted entry '{entry_id}' from vector database."
    except Exception as e:
        return f"Error deleting from vector database: {e}"


def handle_vector_list() -> str:
    if _chroma_collection is None:
        return "Error: vector search not initialized."
    try:
        result = _chroma_collection.get()
        ids = result["ids"]
        if not ids:
            return "Vector database is empty."
        return f"Vector database entries ({len(ids)}):\n" + "\n".join(
            f"- {eid}" for eid in sorted(ids)
        )
    except Exception as e:
        return f"Error listing vector database: {e}"
