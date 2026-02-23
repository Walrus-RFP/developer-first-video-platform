from dotenv import load_dotenv
load_dotenv()  # Load .env before any module reads os.environ

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from data_plane.chunk_upload import router as chunk_router
from control_plane.db import get_video, log_usage
from utils.signing import verify_signed_url
from data_plane.cache import chunk_cache
from data_plane.aggregator import stream_byte_range
from utils.logger import logger

import os
import json
import urllib.request
import urllib.error

CONTROL_PLANE_URL = os.environ.get("CONTROL_PLANE_URL", "http://127.0.0.1:8000")

app = FastAPI()

from control_plane.rate_limit import RateLimitMiddleware

app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chunk_router, prefix="/v1")

STORAGE_DIR = "storage"
HLS_DIR = os.path.join(STORAGE_DIR, "hls")


@app.get("/")
def root():
    return {"message": "Data plane running"}
    

# =========================================================
# BYTE RANGE STREAM (MP4 fallback)
# =========================================================
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


from data_plane.aggregator import stream_byte_range

# =========================================================
# MP4 SIGNED PLAYBACK
# =========================================================
@app.get("/play/{video_id}")
def play_video(video_id: str, request: Request):

    # verify signed URL
    if not verify_signed_url(video_id, request.query_params):
        raise HTTPException(403, "Invalid or expired signed URL")

    # The video metadata confirms the existence of the video, though
    # the actual content is in Walrus chunks.
    video = get_video(video_id)
    if not video:
        raise HTTPException(404, "Video not found")

    # Load the session manifest to find the total video size
    manifest_path = os.path.join(HLS_DIR, video_id, "manifest.json")
    if not os.path.exists(manifest_path):
        raise HTTPException(404, "Manifest missing - cannot stream via chunks")

    with open(manifest_path, "r") as f:
        manifest = json.load(f)

    file_size = sum(c["size"] for c in manifest["chunks"])
    
    range_header = request.headers.get("range")

    if range_header:
        bytes_range = range_header.replace("bytes=", "")
        parts = bytes_range.split("-")

        start = int(parts[0]) if parts[0] else 0
        end = int(parts[1]) if len(parts) > 1 and parts[1] else file_size - 1
        end = min(end, file_size - 1)

        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(end - start + 1),
            "Content-Type": "video/mp4",
        }

        # Log egress usage
        log_usage(video_id, video.get("owner", "unknown"), "egress", end - start + 1)

        return StreamingResponse(
            stream_byte_range(video_id, start, end, encryption_key=video.get("encryption_key")),
            status_code=206,
            headers=headers,
        )

    # Log egress usage
    log_usage(video_id, video.get("owner", "unknown"), "egress", file_size)

    # Note: Full MP4 decryption is expensive for large files.
    # In production, we primarily force HLS for encrypted content.
    return StreamingResponse(
        stream_byte_range(video_id, 0, file_size - 1, encryption_key=video.get("encryption_key")),
        headers={"Content-Type": "video/mp4"},
    )


from fastapi import Response

# =========================================================
# HLS PLAYLIST + SEGMENT SERVING
# =========================================================
@app.get("/play/{video_id}/{file_path:path}")
def serve_hls_file(video_id: str, file_path: str, request: Request):

    # verify signature (the signing logic handles the root filename or the whole path)
    if not verify_signed_url(video_id, request.query_params, file=file_path):
        raise HTTPException(403, "Invalid or expired signed URL")

    # Path traversal protection
    requested_path = os.path.normpath(file_path)
    if requested_path.startswith("..") or os.path.isabs(requested_path):
        raise HTTPException(400, "Invalid file path")

    # 1. Check if we have a local manifest entry for this file
    manifest_path = os.path.join(HLS_DIR, video_id, "manifest.json")
    blob_id = None
    
    # Try local disk first
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r") as f:
                manifest = json.load(f)
            hls_assets = manifest.get("hls_assets", {})
            blob_id = hls_assets.get(requested_path)
        except json.JSONDecodeError:
            logger.error("Corrupted or empty manifest", extra={"video_id": video_id, "path": manifest_path})
            blob_id = None
    else:
        # Fetch manifest from control plane over HTTP (production: separate servers)
        try:
            manifest_url = f"{CONTROL_PLANE_URL}/v1/hls-manifest/{video_id}"
            logger.info("Fetching HLS manifest from control plane", extra={"video_id": video_id, "url": manifest_url})
            req = urllib.request.Request(manifest_url, method="GET")
            req.add_header("User-Agent", "WalrusDataPlane/1.0")
            with urllib.request.urlopen(req) as response:
                manifest = json.loads(response.read().decode('utf-8'))
            
            # Cache locally for subsequent segment requests
            os.makedirs(os.path.join(HLS_DIR, video_id), exist_ok=True)
            with open(manifest_path, "w") as f:
                json.dump(manifest, f, indent=2)
            
            hls_assets = manifest.get("hls_assets", {})
            blob_id = hls_assets.get(requested_path)
            logger.info("Cached manifest locally", extra={"video_id": video_id, "asset_count": len(hls_assets)})
        except Exception as e:
            logger.error("Failed to fetch HLS manifest", extra={"video_id": video_id, "error": str(e)})
            blob_id = None

    if blob_id:
        logger.info("Serving HLS asset", extra={"video_id": video_id, "path": requested_path, "blob_id": blob_id})
        data = chunk_cache.get_chunk(blob_id)
        
        # Seal-based Decryption
        video = get_video(video_id)
        if video and video.get("encryption_key"):
            from utils.crypto import decrypt_data
            try:
                data = decrypt_data(data, video["encryption_key"])
                logger.debug("Decrypted blob data for playback", extra={"video_id": video_id, "path": requested_path})
            except Exception as de:
                logger.error("Failed to decrypt blob", extra={"error": str(de), "video_id": video_id})
                raise HTTPException(500, "Content decryption failed")

        # Log egress usage
        owner = video.get("owner", "unknown") if video else "unknown"
        log_usage(video_id, owner, "egress", len(data))

        if requested_path.endswith(".m3u8"):
            content = data.decode()
            qs = str(request.query_params)
            if qs:
                import re
                content = re.sub(r'([a-zA-Z0-9_\-\./]+\.ts)', rf'\1?{qs}', content)
                content = re.sub(r'([a-zA-Z0-9_\-\./]+\.m3u8)', rf'\1?{qs}', content)
            return Response(
                content=content, 
                media_type="application/vnd.apple.mpegurl",
                headers={"Cache-Control": "public, max-age=60"}
            )

        if requested_path.endswith(".ts"):
            return Response(
                content=data, 
                media_type="video/MP2T",
                headers={"Cache-Control": "public, max-age=31536000, immutable"}
            )
            
        return Response(content=data)

    # 2. Fallback to Local Disk (for older uploads or if upload failed)
    path = os.path.join(HLS_DIR, video_id, requested_path)

    if not os.path.exists(path):
        raise HTTPException(404, f"HLS file not found: {requested_path}")

    # Log egress usage
    video = get_video(video_id)
    owner = video.get("owner", "unknown") if video else "unknown"
    try:
        log_usage(video_id, owner, "egress", os.path.getsize(path))
    except:
        pass

    # playlist vs segment
    if requested_path.endswith(".m3u8"):
        with open(path, "r") as f:
            content = f.read()
        qs = str(request.query_params)
        if qs:
            import re
            content = re.sub(r'([a-zA-Z0-9_\-\./]+\.ts)', rf'\1?{qs}', content)
            content = re.sub(r'([a-zA-Z0-9_\-\./]+\.m3u8)', rf'\1?{qs}', content)
            
        return Response(
            content=content, 
            media_type="application/vnd.apple.mpegurl",
            headers={"Cache-Control": "public, max-age=60"}
        )

    if requested_path.endswith(".ts"):
        return FileResponse(
            path, 
            media_type="video/MP2T",
            headers={"Cache-Control": "public, max-age=31536000, immutable"}
        )

    return FileResponse(path)


# =========================================================
# HEAD request for video players
# =========================================================
@app.head("/play/{video_id}")
def head_video(video_id: str, request: Request):

    if not verify_signed_url(video_id, request.query_params):
        raise HTTPException(403)

    video = get_video(video_id)
    if not video:
        raise HTTPException(404)

    manifest_path = os.path.join(HLS_DIR, video_id, "manifest.json")
    if not os.path.exists(manifest_path):
        raise HTTPException(404, "Manifest missing - cannot stat via chunks")

    with open(manifest_path, "r") as f:
        manifest = json.load(f)

    file_size = sum(c["size"] for c in manifest["chunks"])

    return StreamingResponse(
        iter([]),
        headers={
            "Content-Length": str(file_size),
            "Accept-Ranges": "bytes",
            "Content-Type": "video/mp4"
        }
    )