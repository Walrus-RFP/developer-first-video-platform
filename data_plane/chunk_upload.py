from fastapi import APIRouter, UploadFile, File, HTTPException
import asyncio
import os
import json
import hashlib
import fcntl
from utils.walrus import store_blob

router = APIRouter()
STORAGE_DIR = "storage"
os.makedirs(STORAGE_DIR, exist_ok=True)

# Raw upload chunks are temporary; use a short epoch count.
# The control plane will re-upload HLS assets with a much longer epoch count.
CHUNK_EPOCHS = int(os.getenv("WALRUS_CHUNK_EPOCHS", "5"))


def checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_manifest(manifest_path: str) -> dict:
    if os.path.exists(manifest_path):
        with open(manifest_path, "r") as f:
            return json.load(f)
    return {"chunks": []}


def _write_manifest(manifest_path: str, manifest: dict):
    # Write to a temp file first, then atomically replace to avoid partial writes
    tmp_path = manifest_path + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(manifest, f, indent=2)
    os.replace(tmp_path, manifest_path)


@router.post("/upload-chunk/{session_id}/{chunk_id}/{chunk_index}")
async def upload_chunk(
    session_id: str,
    chunk_id: str,
    chunk_index: int,
    file: UploadFile = File(...),
):
    session_dir = os.path.join(STORAGE_DIR, session_id)
    os.makedirs(session_dir, exist_ok=True)

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(
            status_code=400,
            detail="Uploaded chunk is empty (0 bytes). Check FormData encoding.",
        )

    # Store blob in Walrus — run in a thread so we don't block the async event loop
    try:
        blob_id = await asyncio.get_running_loop().run_in_executor(
            None, lambda: store_blob(content, epochs=CHUNK_EPOCHS)
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to store chunk in Walrus: {e}")

    manifest_path = os.path.join(session_dir, "manifest.json")

    # Use a file-level lock to prevent race conditions from parallel chunk uploads
    lock_path = manifest_path + ".lock"
    with open(lock_path, "w") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            manifest = _read_manifest(manifest_path)
            if "session_id" not in manifest:
                manifest["session_id"] = session_id
            if "chunks" not in manifest:
                manifest["chunks"] = []

            # Idempotent: skip if this chunk_id was already recorded
            for c in manifest["chunks"]:
                if c["chunk_id"] == chunk_id:
                    return {"status": "chunk already stored", "chunk_index": chunk_index}

            manifest["chunks"].append({
                "chunk_id": chunk_id,
                "chunk_index": chunk_index,
                "blob_id": blob_id,
                "checksum": checksum(content),
                "size": len(content),
            })

            manifest["chunks"].sort(key=lambda x: x["chunk_index"])
            _write_manifest(manifest_path, manifest)
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)

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
