from fastapi import APIRouter
import uuid
import os
import json

router = APIRouter()

UPLOAD_SESSIONS = {}
STORAGE_DIR = "storage"

@router.post("/upload-session")
def create_upload_session():
    session_id = str(uuid.uuid4())
    UPLOAD_SESSIONS[session_id] = {"status": "created"}
    return {"upload_session_id": session_id}

@router.post("/complete-upload/{session_id}")
def complete_upload(session_id: str):
    session_dir = os.path.join(STORAGE_DIR, session_id)
    manifest_path = os.path.join(session_dir, "manifest.json")

    if not os.path.exists(manifest_path):
        return {"error": "No chunks uploaded"}

    with open(manifest_path) as f:
        manifest = json.load(f)

    return {
        "status": "upload completed",
        "total_chunks": len(manifest["chunks"])
    }

@router.get("/upload-status/{session_id}")
def upload_status(session_id: str):
    import os, json

    manifest_path = f"storage/{session_id}/manifest.json"

    if not os.path.exists(manifest_path):
        return {"uploaded_chunks": []}

    with open(manifest_path) as f:
        manifest = json.load(f)

    return {
        "uploaded_chunks": [c["chunk_id"] for c in manifest["chunks"]]
    }
