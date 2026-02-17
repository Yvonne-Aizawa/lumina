"""Vector database route handlers."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..auth import require_auth
from ..tools._vector import get_collection

router = APIRouter()


class VectorUpdateRequest(BaseModel):
    content: str
    metadata: dict | None = None


@router.get("/api/vector", dependencies=[Depends(require_auth)])
async def api_vector_list():
    col = get_collection()
    if col is None:
        return {"error": "Vector search not initialized."}
    result = col.get(include=["documents", "metadatas"])
    entries = []
    for i, eid in enumerate(result["ids"]):
        entries.append(
            {
                "id": eid,
                "content": result["documents"][i] if result["documents"] else "",
                "metadata": result["metadatas"][i] if result["metadatas"] else {},
            }
        )
    return {"entries": entries}


@router.get("/api/vector/{entry_id}", dependencies=[Depends(require_auth)])
async def api_vector_get(entry_id: str):
    col = get_collection()
    if col is None:
        return {"error": "Vector search not initialized."}
    result = col.get(ids=[entry_id], include=["documents", "metadatas"])
    if not result["ids"]:
        return {"error": f"Entry '{entry_id}' not found."}
    return {
        "id": result["ids"][0],
        "content": result["documents"][0] if result["documents"] else "",
        "metadata": result["metadatas"][0] if result["metadatas"] else {},
    }


@router.put("/api/vector/{entry_id}", dependencies=[Depends(require_auth)])
async def api_vector_update(entry_id: str, req: VectorUpdateRequest):
    col = get_collection()
    if col is None:
        return {"error": "Vector search not initialized."}
    existing = col.get(ids=[entry_id])
    if not existing["ids"]:
        return {"error": f"Entry '{entry_id}' not found."}
    metadata = req.metadata if req.metadata else None
    col.upsert(
        ids=[entry_id],
        documents=[req.content],
        metadatas=[metadata] if metadata else None,
    )
    return {"status": "ok", "id": entry_id}


@router.delete("/api/vector/{entry_id}", dependencies=[Depends(require_auth)])
async def api_vector_delete(entry_id: str):
    col = get_collection()
    if col is None:
        return {"error": "Vector search not initialized."}
    col.delete(ids=[entry_id])
    return {"status": "ok", "id": entry_id}
