from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse, Response, HTMLResponse
from data_plane.chunk_upload import router as chunk_router
from control_plane.db import get_video, log_usage
from utils.signing import verify_signed_url
from data_plane.cache import chunk_cache
from data_plane.aggregator import stream_byte_range
from utils.logger import logger

import os
import re
import json
import urllib.request
import urllib.error

CONTROL_PLANE_URL = os.environ.get("CONTROL_PLANE_URL", "http://127.0.0.1:8000")

app = FastAPI(
    title="Walrus Video Platform — Data Plane",
    description=(
        "Chunk upload ingestion, HLS playlist and segment serving, "
        "HMAC-signed URL verification, Walrus blob retrieval with "
        "RAM+disk LRU cache, and byte-range MP4 streaming. "
        "Interactive docs at /docs · ReDoc at /redoc."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

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

@app.get("/v1/debug-logs")
def get_logs():
    try:
        with open("app.log", "r") as f:
            lines = f.readlines()
            return {"logs": "".join(lines[-100:])}
    except Exception as e:
        return {"error": str(e)}


# =========================================================
# EMBED PLAYER PAGE (served in iframes)
# =========================================================
@app.get("/embed/{video_id}", response_class=HTMLResponse)
def embed_player(video_id: str, playlist: str = None):
    """
    Minimal self-contained HLS player page for embedding via <iframe>.
    Accepts ?playlist=<signed_url> or fetches a fresh signed URL from control plane.
    """
    if not playlist:
        try:
            url = f"{CONTROL_PLANE_URL}/v1/playback-url/{video_id}"
            req = urllib.request.Request(url, method="GET")
            req.add_header("User-Agent", "WalrusDataPlane/1.0")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
            playlist = data.get("playlist", "")
        except Exception as e:
            logger.warning("embed: could not get playback URL for %s: %s", video_id, e)
            raise HTTPException(404, "Video not found or unavailable")

    safe_playlist = json.dumps(playlist)
    html = f"""<!DOCTYPE html>
<html lang="en"><head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Video Player</title>
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ background: #000; width: 100vw; height: 100vh; display: flex; align-items: center; justify-content: center; overflow: hidden; }}
    video {{ width: 100%; height: 100%; object-fit: contain; }}
  </style>
</head><body>
  <video id="v" controls playsinline autoplay></video>
  <script src="https://cdn.jsdelivr.net/npm/hls.js@latest/dist/hls.min.js"></script>
  <script>
    var src = {safe_playlist};
    var video = document.getElementById('v');
    if (Hls.isSupported()) {{
      var hls = new Hls();
      hls.loadSource(src);
      hls.attachMedia(video);
      hls.on(Hls.Events.MANIFEST_PARSED, function() {{ video.play().catch(function(){{}}); }});
    }} else if (video.canPlayType('application/vnd.apple.mpegurl')) {{
      video.src = src;
      video.play().catch(function(){{}});
    }}
  </script>
</body></html>"""
    return HTMLResponse(content=html, headers={"X-Frame-Options": "ALLOWALL"})


# =========================================================
# MP4 SIGNED PLAYBACK (byte-range streaming)
# =========================================================
@app.get("/play/{video_id}")
def play_video(video_id: str, request: Request):

    if not verify_signed_url(video_id, request.query_params):
        raise HTTPException(403, "Invalid or expired signed URL")

    manifest_path = os.path.join(HLS_DIR, video_id, "manifest.json")
    if not os.path.exists(manifest_path):
        raise HTTPException(404, "Manifest missing - cannot stream via chunks")

    with open(manifest_path, "r") as f:
        manifest = json.load(f)

    file_size = sum(c["size"] for c in manifest["chunks"])
    encryption_key = request.query_params.get("key")
    range_header = request.headers.get("range")

    if range_header:
        bytes_range = range_header.replace("bytes=", "")
        parts = bytes_range.split("-")
        start = int(parts[0]) if parts[0] else 0
        end = int(parts[1]) if len(parts) > 1 and parts[1] else file_size - 1
        end = min(end, file_size - 1)

        # Log egress
        try:
            log_usage(video_id, "unknown", "egress", end - start + 1)
        except Exception:
            pass

        return StreamingResponse(
            stream_byte_range(video_id, start, end, encryption_key=encryption_key),
            status_code=206,
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(end - start + 1),
                "Content-Type": "video/mp4",
            },
        )

    # Full file response (no Range header)
    try:
        log_usage(video_id, "unknown", "egress", file_size)
    except Exception:
        pass

    return StreamingResponse(
        stream_byte_range(video_id, 0, file_size - 1, encryption_key=encryption_key),
        headers={
            "Content-Type": "video/mp4",
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size),
        },
    )


# =========================================================
# HLS PLAYLIST + SEGMENT SERVING
# =========================================================
@app.get("/play/{video_id}/{file_path:path}")
def serve_hls_file(video_id: str, file_path: str, request: Request):

    if not verify_signed_url(video_id, request.query_params, file=file_path):
        raise HTTPException(403, "Invalid or expired signed URL")

    # Path traversal protection
    requested_path = os.path.normpath(file_path)
    if requested_path.startswith("..") or os.path.isabs(requested_path):
        raise HTTPException(400, "Invalid file path")

    # ── 1. Resolve blob_id from manifest ────────────────────────────────────
    manifest_path = os.path.join(HLS_DIR, video_id, "manifest.json")
    blob_id = None

    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r") as f:
                manifest = json.load(f)
            hls_assets = manifest.get("hls_assets", {})
            blob_id = hls_assets.get(requested_path)
        except json.JSONDecodeError:
            logger.error("Corrupted manifest", extra={"video_id": video_id, "path": manifest_path})
            blob_id = None
    else:
        # Fetch from control plane and cache locally
        try:
            manifest_url = f"{CONTROL_PLANE_URL}/v1/hls-manifest/{video_id}"
            logger.info("Fetching HLS manifest from control plane",
                        extra={"video_id": video_id, "url": manifest_url})
            req = urllib.request.Request(manifest_url, method="GET")
            req.add_header("User-Agent", "WalrusDataPlane/1.0")
            with urllib.request.urlopen(req, timeout=10) as response:
                manifest = json.loads(response.read().decode("utf-8"))

            os.makedirs(os.path.join(HLS_DIR, video_id), exist_ok=True)
            with open(manifest_path, "w") as f:
                json.dump(manifest, f, indent=2)

            hls_assets = manifest.get("hls_assets", {})
            blob_id = hls_assets.get(requested_path)
            logger.info("Cached manifest locally",
                        extra={"video_id": video_id, "asset_count": len(hls_assets)})
        except Exception as e:
            logger.error("Failed to fetch HLS manifest",
                         extra={"video_id": video_id, "error": str(e)})

    # ── 2. Serve from Walrus via cache ──────────────────────────────────────
    if blob_id:
        logger.info("Serving HLS asset from Walrus",
                    extra={"video_id": video_id, "path": requested_path, "blob_id": blob_id})
        data = chunk_cache.get_chunk(blob_id)

        encryption_key = request.query_params.get("key")
        if encryption_key:
            from utils.crypto import decrypt_data
            try:
                data = decrypt_data(data, encryption_key)
            except Exception as de:
                logger.error("Failed to decrypt blob",
                             extra={"error": str(de), "video_id": video_id})
                raise HTTPException(500, "Content decryption failed")

        try:
            log_usage(video_id, "unknown", "egress", len(data))
        except Exception:
            pass

        if requested_path.endswith(".m3u8"):
            content = data.decode()
            qs = str(request.query_params)
            if qs:
                content = re.sub(r"([a-zA-Z0-9_\-\./]+\.ts)", rf"\1?{qs}", content)
                content = re.sub(r"([a-zA-Z0-9_\-\./]+\.m3u8)", rf"\1?{qs}", content)
            # Playlists must NOT be cached — they contain signed query params
            return Response(
                content=content,
                media_type="application/vnd.apple.mpegurl",
                headers={"Cache-Control": "no-store"},
            )

        if requested_path.endswith(".ts"):
            return Response(
                content=data,
                media_type="video/MP2T",
                headers={"Cache-Control": "public, max-age=31536000, immutable"},
            )

        return Response(content=data)

    # ── 3. Fallback: serve from local disk ──────────────────────────────────
    path = os.path.join(HLS_DIR, video_id, requested_path)
    if not os.path.exists(path):
        raise HTTPException(404, f"HLS file not found: {requested_path}")

    try:
        log_usage(video_id, "unknown", "egress", os.path.getsize(path))
    except Exception:
        pass

    if requested_path.endswith(".m3u8"):
        with open(path, "r") as f:
            content = f.read()
        qs = str(request.query_params)
        if qs:
            content = re.sub(r"([a-zA-Z0-9_\-\./]+\.ts)", rf"\1?{qs}", content)
            content = re.sub(r"([a-zA-Z0-9_\-\./]+\.m3u8)", rf"\1?{qs}", content)
        return Response(
            content=content,
            media_type="application/vnd.apple.mpegurl",
            headers={"Cache-Control": "no-store"},
        )

    if requested_path.endswith(".ts"):
        return FileResponse(
            path,
            media_type="video/MP2T",
            headers={"Cache-Control": "public, max-age=31536000, immutable"},
        )

    return FileResponse(path)


# =========================================================
# SEAL KEY BLOB ENDPOINTS
# =========================================================
from utils.walrus import store_blob, read_blob as walrus_read_blob

@app.post("/v1/seal-blob")
async def upload_seal_blob(request: Request):
    """
    Upload a small blob (Seal-encrypted AES key) to Walrus.
    Returns the blob_id for the caller to store in the platform DB.
    Requires no auth — the blob is encrypted with Seal; only authorised
    viewers can decrypt it via the Seal SDK.
    """
    data = await request.body()
    if not data:
        raise HTTPException(400, "Empty body")
    if len(data) > 1 * 1024 * 1024:  # 1 MB max for key blobs
        raise HTTPException(413, "Blob too large for a key blob")
    try:
        hls_epochs = int(os.getenv("WALRUS_HLS_EPOCHS", "50"))
        blob_id = store_blob(data, epochs=hls_epochs)
        return {"blob_id": blob_id}
    except Exception as e:
        logger.error("seal-blob upload failed", extra={"error": str(e)})
        raise HTTPException(502, f"Walrus upload failed: {e}")


@app.get("/v1/seal-blob/{blob_id}")
def download_seal_blob(blob_id: str):
    """
    Download a Seal-encrypted key blob from Walrus.
    Returns raw bytes. The blob is Seal-encrypted so it is safe to serve publicly.
    """
    try:
        data = walrus_read_blob(blob_id)
        return Response(content=data, media_type="application/octet-stream")
    except Exception as e:
        logger.error("seal-blob download failed", extra={"blob_id": blob_id, "error": str(e)})
        raise HTTPException(404, f"Blob not found: {e}")


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

    # Try to get file size from manifest; fall back to DB
    manifest_path = os.path.join(HLS_DIR, video_id, "manifest.json")
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r") as f:
                manifest = json.load(f)
            file_size = sum(c["size"] for c in manifest.get("chunks", []))
        except Exception:
            file_size = video.get("file_size") or 0
    else:
        file_size = video.get("file_size") or 0

    return StreamingResponse(
        iter([]),
        headers={
            "Content-Length": str(file_size),
            "Accept-Ranges": "bytes",
            "Content-Type": "video/mp4",
        },
    )
