from fastapi import APIRouter, UploadFile, File, HTTPException
import os
import json
import hashlib

router = APIRouter()
STORAGE_DIR = "storage"
os.makedirs(STORAGE_DIR, exist_ok=True)

def checksum(data):
    return hashlib.sha256(data).hexdigest()

#UNDERSTOOD TILL HERE

@router.post("/upload-chunk/{session_id}/{chunk_id}/{chunk_index}")
async def upload_chunk(
    session_id: str,
    chunk_id: str,
    chunk_index: int,
    file: UploadFile = File(...)
):
    session_dir = os.path.join(STORAGE_DIR, session_id)
    os.makedirs(session_dir, exist_ok=True)

    file_path = os.path.join(session_dir, chunk_id)

    content = await file.read()

    manifest_path = os.path.join(session_dir, "manifest.json")

    if os.path.exists(manifest_path):
        with open(manifest_path, "r") as f:
            manifest = json.load(f)
    else:
        manifest = {"session_id": session_id, "chunks": []}

    for c in manifest["chunks"]:
        if c["chunk_id"] == chunk_id:
            raise HTTPException(status_code=400, detail="Chunk already uploaded")

    with open(file_path, "wb") as f:
        f.write(content)

    manifest["chunks"].append({
        "chunk_id": chunk_id,
        "chunk_index": chunk_index,
        "checksum": checksum(content),
        "size": len(content)
    })

    manifest["chunks"].sort(key=lambda x: x["chunk_index"])

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    return {"status": "chunk stored", "chunk_index": chunk_index}
