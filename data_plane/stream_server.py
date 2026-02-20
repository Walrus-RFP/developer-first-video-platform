from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from data_plane.chunk_upload import router as chunk_router
from control_plane.db import get_video
from utils.signing import verify_signed_url

import os
import json

app = FastAPI()
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

    chunks = sorted(
        manifest.get("chunks", []),
        key=lambda c: c.get("chunk_index", 0)
    )

    return [os.path.join(session_dir, c["chunk_id"]) for c in chunks]


# ---------------------------------------------------
# Helper: byte range streaming
# ---------------------------------------------------
def range_stream(file_path, start, end):
    with open(file_path, "rb") as f:
        f.seek(start)
        remaining = end - start + 1
        chunk_size = 1024 * 1024

        while remaining > 0:
            read_size = min(chunk_size, remaining)
            data = f.read(read_size)
            if not data:
                break
            remaining -= len(data)
            yield data


# ---------------------------------------------------
# Playback Endpoint
# ---------------------------------------------------
@app.get("/play/{video_id}")
def play_video(video_id: str, request: Request):

    # ✅ 1. Verify signed URL
    if not verify_signed_url(video_id, request.query_params):
        raise HTTPException(status_code=403, detail="Invalid or expired signed URL")

    # ✅ 2. Fetch metadata
    video = get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    file_path = video["file_path"]

    # =================================================
    # CASE 1 — merged file exists → BYTE RANGE STREAM
    # =================================================
    if os.path.exists(file_path):

        file_size = os.path.getsize(file_path)
        range_header = request.headers.get("range")

        if range_header:
            try:
                bytes_range = range_header.replace("bytes=", "")
                parts = bytes_range.split("-")

                start = int(parts[0]) if parts[0] else 0
                end = int(parts[1]) if len(parts) > 1 and parts[1] else file_size - 1

                if start >= file_size:
                    raise HTTPException(status_code=416)

                end = min(end, file_size - 1)

                headers = {
                    "Content-Range": f"bytes {start}-{end}/{file_size}",
                    "Accept-Ranges": "bytes",
                    "Content-Length": str(end - start + 1),
                    "Content-Type": "video/mp4",
                }

                return StreamingResponse(
                    range_stream(file_path, start, end),
                    status_code=206,
                    headers=headers,
                )

            except Exception:
                raise HTTPException(status_code=400, detail="Invalid Range header")

        # no range → full stream
        return StreamingResponse(
            range_stream(file_path, 0, file_size - 1),
            headers={"Content-Type": "video/mp4"},
        )

    # =================================================
    # CASE 2 — fallback chunk streaming
    # =================================================
    try:
        session_id = os.path.basename(os.path.dirname(file_path))
        chunk_paths = get_chunk_paths(session_id)

        def stream():
            for path in chunk_paths:
                with open(path, "rb") as f:
                    yield f.read()

        return StreamingResponse(stream(), media_type="video/mp4")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    
@app.head("/play/{video_id}")
def head_video(video_id: str, request: Request):
    if not verify_signed_url(video_id, request.query_params):
        raise HTTPException(status_code=403)

    video = get_video(video_id)
    if not video:
        raise HTTPException(status_code=404)

    file_path = video["file_path"]
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404)

    size = os.path.getsize(file_path)

    return StreamingResponse(
        iter([]),
        headers={
            "Content-Length": str(size),
            "Accept-Ranges": "bytes",
            "Content-Type": "video/mp4"
        }
    )