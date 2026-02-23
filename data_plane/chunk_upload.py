from fastapi import APIRouter, UploadFile, File, HTTPException
import os
import json
import hashlib
from utils.walrus import store_blob

router = APIRouter()
STORAGE_DIR = "storage"
os.makedirs(STORAGE_DIR, exist_ok=True)

def checksum(data):
    return hashlib.sha256(data).hexdigest()



@router.post("/upload-chunk/{session_id}/{chunk_id}/{chunk_index}")
async def upload_chunk(
    session_id: str,
    chunk_id: str,
    chunk_index: int,
    file: UploadFile = File(...)
):
    session_dir = os.path.join(STORAGE_DIR, session_id)
    os.makedirs(session_dir, exist_ok=True)

    # Local file_path no longer needed for data, but can keep for backwards compatibility 
    # if we wanted to dual-write. For now we only write to Walrus.

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Uploaded chunk is empty (0 bytes). Check FormData encoding.")

    manifest_path = os.path.join(session_dir, "manifest.json")

    if os.path.exists(manifest_path):
        with open(manifest_path, "r") as f:
            manifest = json.load(f)
    else:
        manifest = {"session_id": session_id, "chunks": []}

    for c in manifest["chunks"]:
        if c["chunk_id"] == chunk_id:
            raise HTTPException(status_code=400, detail="Chunk already uploaded")

    # Store blob in Walrus
    blob_id = store_blob(content)

    manifest["chunks"].append({
        "chunk_id": chunk_id,
        "chunk_index": chunk_index,
        "blob_id": blob_id,
        "checksum": checksum(content),
        "size": len(content)
    })

    manifest["chunks"].sort(key=lambda x: x["chunk_index"])

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    return {"status": "chunk stored", "chunk_index": chunk_index}


@router.get("/manifest/{session_id}")
def get_manifest(session_id: str):
    session_dir = os.path.join(STORAGE_DIR, session_id)
    manifest_path = os.path.join(session_dir, "manifest.json")

    if not os.path.exists(manifest_path):
        raise HTTPException(status_code=404, detail="manifest not found")

    with open(manifest_path, "r") as f:
        return json.load(f)


@router.get("/upload-session/{session_id}")
def get_upload_session(session_id: str):
    """Returns which chunks have been uploaded, enabling resumable uploads."""
    session_dir = os.path.join(STORAGE_DIR, session_id)
    manifest_path = os.path.join(session_dir, "manifest.json")

    if not os.path.exists(manifest_path):
        return {
            "session_id": session_id,
            "status": "created",
            "uploaded_chunks": [],
            "total_uploaded": 0,
        }

    with open(manifest_path, "r") as f:
        manifest = json.load(f)

    chunks = manifest.get("chunks", [])
    return {
        "session_id": session_id,
        "status": "uploading",
        "uploaded_chunks": sorted([c["chunk_index"] for c in chunks]),
        "total_uploaded": len(chunks),
    }
