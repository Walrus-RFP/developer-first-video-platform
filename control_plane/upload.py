from fastapi import APIRouter, HTTPException
import uuid
import os
import json
from control_plane.db import create_video
from control_plane.db import create_video, list_videos
from control_plane.db import get_video
import hashlib
from control_plane.db import create_video, get_video_by_checksum

router = APIRouter()

STORAGE_DIR = "storage"
UPLOAD_SESSIONS = {}

os.makedirs(STORAGE_DIR, exist_ok=True)

def file_checksum(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()
# ---------------------------------------------------
# Create Upload Session
# ---------------------------------------------------
@router.post("/upload-session")
def create_upload_session():
    session_id = str(uuid.uuid4())

    session_dir = os.path.join(STORAGE_DIR, session_id)
    os.makedirs(session_dir, exist_ok=True)

    UPLOAD_SESSIONS[session_id] = {
        "status": "created",
        "session_dir": session_dir
    }

    return {"upload_session_id": session_id}


# ---------------------------------------------------
# Merge Chunks
# ---------------------------------------------------
def merge_chunks(session_id: str, output_name="final_video.bin"):
    session_dir = os.path.join(STORAGE_DIR, session_id)
    manifest_path = os.path.join(session_dir, "manifest.json")

    if not os.path.exists(manifest_path):
        raise Exception("No chunks uploaded")

    with open(manifest_path, "r") as f:
        manifest = json.load(f)

    chunks = manifest.get("chunks", [])

    if len(chunks) == 0:
        raise Exception("No chunks uploaded")

    # Sort by chunk index
    chunks = sorted(chunks, key=lambda x: x.get("chunk_index", 0))

    output_path = os.path.join(session_dir, output_name)

    with open(output_path, "wb") as outfile:
        for chunk in chunks:
            chunk_file = os.path.join(session_dir, chunk["chunk_id"])

            if not os.path.exists(chunk_file):
                raise Exception(f"Missing chunk {chunk['chunk_id']}")

            with open(chunk_file, "rb") as infile:
                outfile.write(infile.read())

    return output_path


# ---------------------------------------------------
# Complete Upload
# ---------------------------------------------------
@router.post("/complete-upload/{session_id}")
def complete_upload(session_id: str):

    if session_id not in UPLOAD_SESSIONS:
        raise HTTPException(status_code=404, detail="Invalid session")

    if UPLOAD_SESSIONS[session_id]["status"] == "completed":
        return {"status": "already completed"}

    try:
        final_file = merge_chunks(session_id)

        # 🔥 compute checksum
        hash_val = file_checksum(final_file)

        # 🔥 check reuse
        existing = get_video_by_checksum(hash_val)
        if existing:
            UPLOAD_SESSIONS[session_id]["status"] = "completed"

            return {
                "status": "reused existing asset",
                "video_id": existing["video_id"],
                "file": existing["file_path"]
            }

        # 🔥 create new video
        video_id = create_video(
            owner="test_user",
            file_path=final_file,
            checksum=hash_val
        )

        UPLOAD_SESSIONS[session_id]["status"] = "completed"

        return {
            "status": "upload completed",
            "video_id": video_id,
            "final_file": final_file
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
# ---------------------------------------------------
# Upload Status (for resume)
# ---------------------------------------------------
@router.get("/upload-status/{session_id}")
def upload_status(session_id: str):

    manifest_path = os.path.join(STORAGE_DIR, session_id, "manifest.json")

    if not os.path.exists(manifest_path):
        return {"uploaded_chunks": []}

    with open(manifest_path) as f:
        manifest = json.load(f)

    return {
        "uploaded_chunks": [
            {
                "chunk_id": c["chunk_id"],
                "chunk_index": c.get("chunk_index", 0)
            }
            for c in manifest.get("chunks", [])
        ]
    }
    
@router.get("/videos")
def get_videos():
    return {"videos": list_videos()}


@router.get("/playback-url/{video_id}")
def playback_url(video_id: str):
    video = get_video(video_id)

    if not video:
        return {"error": "Video not found"}

    playback = f"http://127.0.0.1:8001/play/{video_id}"

    return {
        "video_id": video_id,
        "playback_url": playback
    }
