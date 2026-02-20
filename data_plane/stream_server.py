from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from data_plane.chunk_upload import router as chunk_router
from control_plane.db import get_video
import os
import json

app = FastAPI()

# existing chunk upload routes
app.include_router(chunk_router)

STORAGE_DIR = "storage"


@app.get("/")
def root():
    return {"message": "Data plane running"}


# ---------------------------------------------------
# Helper: get chunk paths from manifest
# ---------------------------------------------------
def get_chunk_paths(session_id: str):
    session_dir = os.path.join(STORAGE_DIR, session_id)
    manifest_path = os.path.join(session_dir, "manifest.json")

    if not os.path.exists(manifest_path):
        raise Exception("Manifest not found")

    with open(manifest_path) as f:
        manifest = json.load(f)

    chunks = manifest.get("chunks", [])

    if not chunks:
        raise Exception("No chunks in manifest")

    # sort by chunk_index
    chunks = sorted(chunks, key=lambda c: c.get("chunk_index", 0))

    return [os.path.join(session_dir, c["chunk_id"]) for c in chunks]


# ---------------------------------------------------
# Playback Endpoint
# ---------------------------------------------------
@app.get("/play/{video_id}")
def play_video(video_id: str):

    video = get_video(video_id)

    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    file_path = video["file_path"]

    # ✅ CASE 1 — merged file exists
    if os.path.exists(file_path):
        return FileResponse(file_path, media_type="video/mp4")

    # ✅ CASE 2 — fallback to chunk streaming
    try:
        # assume session_id == video_id for now
        chunk_paths = get_chunk_paths(video_id)

        def stream():
            for path in chunk_paths:
                with open(path, "rb") as f:
                    yield f.read()

        return StreamingResponse(stream(), media_type="video/mp4")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))