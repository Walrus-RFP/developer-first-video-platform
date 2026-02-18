from fastapi import APIRouter, UploadFile, File
import os
import json
import hashlib

router = APIRouter()
STORAGE_DIR = "storage"

os.makedirs(STORAGE_DIR, exist_ok=True)

def checksum(data):
    return hashlib.sha256(data).hexdigest()

@router.post("/upload-chunk/{session_id}/{chunk_id}")
async def upload_chunk(session_id: str, chunk_id: str, file: UploadFile = File(...)):
    session_dir = os.path.join(STORAGE_DIR, session_id)
    os.makedirs(session_dir, exist_ok=True)

    file_path = os.path.join(session_dir, chunk_id)

    content = await file.read()

    with open(file_path, "wb") as f:
        f.write(content)

    # ---- update manifest ----
    manifest_path = os.path.join(session_dir, "manifest.json")

    if os.path.exists(manifest_path):
        with open(manifest_path, "r") as f:
            manifest = json.load(f)
    else:
        manifest = {
            "session_id": session_id,
            "chunks": []
        }

    manifest["chunks"].append({
        "chunk_id": chunk_id,
        "checksum": checksum(content),
        "size": len(content)
    })

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    return {"status": "chunk stored"}
