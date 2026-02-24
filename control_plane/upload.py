from utils.logger import logger
logger.info("Upload router loaded")

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
import uuid
import os
import json
import hashlib
import shutil
import subprocess
import urllib.request
import urllib.error
from typing import Optional
from pydantic import BaseModel
from utils.walrus import read_blob, store_blob, with_retries

DATA_PLANE_URL = os.environ.get("DATA_PLANE_URL", "http://127.0.0.1:8001")

# Server-side Validation Constants
MAX_VIDEO_SIZE_MB = 1000  # 1GB limit
ALLOWED_VIDEO_CODECS = {"h264", "hevc", "vp9", "av1"}
ALLOWED_AUDIO_CODECS = {"aac", "mp3", "opus", "vorbis"}

from control_plane.db import (
    create_video,
    list_videos,
    get_video,
    get_video_by_checksum,
    update_video,
    delete_video,
)

from utils.signing import create_signed_url
from utils.sui import is_authorized as check_sui_auth
from control_plane.webhooks import fire_event
from control_plane.auth import get_current_user

router = APIRouter()

# Configuration
STORAGE_DIR = "storage"
UPLOAD_DIR = os.path.join(STORAGE_DIR, "uploads")
HLS_DIR = os.path.join(STORAGE_DIR, "hls")
DATA_PLANE = os.getenv("DATA_PLANE_URL", "http://127.0.0.1:8001")
PUBLIC_DATA_PLANE = os.getenv("PUBLIC_DATA_PLANE_URL", "http://localhost:8001")
AGGREGATOR = os.getenv("WALRUS_AGGREGATOR", "https://aggregator.testnet.sui.io:443")
PUBLISHER = os.getenv("WALRUS_PUBLISHER", "https://publisher.testnet.sui.io:443")

os.makedirs(STORAGE_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(HLS_DIR, exist_ok=True)

# Async Status tracking in-memory (in production, use Redis or Postgres)
# dict of session_id -> { "status": str, "video_id": str, "error": str, "sui_package_id": str, ... }
UPLOAD_STATUS = {}


# ---------------------------------------------------
# CREATE UPLOAD SESSION
# ---------------------------------------------------
@router.post("/upload-session")
def create_upload_session(owner: str = Depends(get_current_user)):
    session_id = str(uuid.uuid4())
    session_dir = os.path.join(STORAGE_DIR, session_id)
    os.makedirs(session_dir, exist_ok=True)

    return {
        "upload_session_id": session_id,
        "upload_path": session_dir
    }


# ---------------------------------------------------
# checksum
# ---------------------------------------------------
def file_checksum(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------
# MP4 → HLS
# ---------------------------------------------------
def convert_to_hls(input_path: str, video_id: str):

    output_dir = os.path.join(HLS_DIR, video_id)
    os.makedirs(output_dir, exist_ok=True)

    FFMPEG = shutil.which("ffmpeg") or "ffmpeg"

    # Define ABR variants
    variants = [
        {"name": "1080p", "w": 1920, "h": 1080, "b": "5000k"},
        {"name": "720p", "w": 1280, "h": 720, "b": "2800k"},
        {"name": "480p", "w": 854, "h": 480, "b": "1400k"}
    ]

    master_playlist_content = "#EXTM3U\n#EXT-X-VERSION:3\n"

    for v in variants:
        variant_dir = os.path.join(output_dir, v["name"])
        os.makedirs(variant_dir, exist_ok=True)
        
        variant_playlist = os.path.join(variant_dir, "index.m3u8")
        
        cmd = [
            FFMPEG,
            "-nostdin",
            "-i", input_path,
            "-vf", f"scale=-2:{v['h']}",
            "-c:v", "libx264",
            "-profile:v", "main",
            "-crf", "23",
            "-preset", "veryfast",
            "-b:v", v["b"],
            "-maxrate", v["b"],
            "-bufsize", v["b"],
            "-c:a", "aac",
            "-b:a", "128k",
            "-f", "hls",
            "-hls_time", "4",
            "-hls_playlist_type", "vod",
            "-hls_segment_filename", os.path.join(variant_dir, "segment_%03d.ts"),
            variant_playlist,
        ]

        logger.info("Generating %s variant", v['name'], extra={"video_id": video_id})
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            logger.error("FFmpeg error: %s", res.stderr, extra={"video_id": video_id})
            res.check_returncode()
        
        # Calculate bandwidth in bps
        bandwidth = int(v["b"].replace("k", "000")) + 128000
        master_playlist_content += f"#EXT-X-STREAM-INF:BANDWIDTH={bandwidth},RESOLUTION={v['w']}x{v['h']}\n"
        master_playlist_content += f"{v['name']}/index.m3u8\n"

    master_path = os.path.join(output_dir, "playlist.m3u8")
    with open(master_path, "w") as f:
        f.write(master_playlist_content)

    return master_path


# ---------------------------------------------------
# THUMBNAIL GENERATION (ffmpeg)
# ---------------------------------------------------
def generate_thumbnail(input_path: str, output_dir: str, video_id: str):
    """Extract a single frame from the video to serve as a thumbnail."""
    FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
    thumb_path = os.path.join(output_dir, "thumbnail.jpg")
    
    cmd = [
        FFMPEG,
        "-y",
        "-nostdin",
        "-i", input_path,
        "-ss", "00:00:01.000", # Capture at 1 second mark
        "-vframes", "1",
        "-vf", "scale=1280:-2", # Scale to 720p equivalent
        "-q:v", "2", # High quality JPEG
        thumb_path
    ]
    
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if res.returncode != 0:
            logger.error("Thumbnail generation failed: %s", res.stderr, extra={"video_id": video_id})
        elif os.path.exists(thumb_path):
            logger.info("Generated thumbnail: %s", thumb_path, extra={"video_id": video_id})
            return thumb_path
    except subprocess.TimeoutExpired:
        logger.error("Thumbnail FFmpeg timeout", extra={"video_id": video_id})
    except Exception as e:
        logger.error("Thumbnail error: %s", e, extra={"video_id": video_id})
        
    return None


# ---------------------------------------------------
# PROBE VIDEO METADATA (ffprobe)
# ---------------------------------------------------
def probe_video_metadata(file_path: str) -> dict:
    """Extract duration, resolution, codecs, and file size using ffprobe."""
    result = {
        "duration_seconds": None, 
        "resolution": None, 
        "file_size": None,
        "video_codec": None,
        "audio_codec": None
    }
    try:
        result["file_size"] = os.path.getsize(file_path)
    except OSError:
        pass

    FFPROBE = shutil.which("ffprobe") or "ffprobe"
    cmd = [
        FFPROBE, "-v", "quiet",
        "-print_format", "json",
        "-show_format", "-show_streams",
        file_path
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if proc.returncode == 0:
            info = json.loads(proc.stdout)
            fmt = info.get("format", {})
            duration = fmt.get("duration")
            if duration:
                result["duration_seconds"] = round(float(duration), 2)

            for stream in info.get("streams", []):
                if stream.get("codec_type") == "video":
                    result["video_codec"] = stream.get("codec_name")
                    w = stream.get("width")
                    h = stream.get("height")
                    if w and h:
                        result["resolution"] = f"{w}x{h}"
                elif stream.get("codec_type") == "audio":
                    result["audio_codec"] = stream.get("codec_name")
    except Exception as e:
        logger.warning("ffprobe failed: %s", e)

    return result


def validate_video_assets(file_path: str):
    """
    Enforces server-side rules on uploaded movies.
    Raises Exception if validation fails.
    """
    meta = probe_video_metadata(file_path)
    
    # 1. Size Check
    size_mb = (meta["file_size"] or 0) / (1024 * 1024)
    if size_mb > MAX_VIDEO_SIZE_MB:
        raise ValueError(f"Video file too large: {size_mb:.1f}MB (Max: {MAX_VIDEO_SIZE_MB}MB)")

    # 2. Corrupt/Empty Check
    if not meta["video_codec"]:
        raise ValueError("Invalid video file: No video stream detected or file is corrupted")

    # 3. Codec Check (Optional but recommended for consistency)
    if meta["video_codec"] not in ALLOWED_VIDEO_CODECS:
         logger.warning("Unsupported video codec: %s", meta['video_codec'])
         # We allow it in this version but transcode will handle it or fail later.
         # For strict enforcement: raise ValueError(f"Codec {meta['video_codec']} not allowed")

    return meta


# ---------------------------------------------------
# Merge chunks
# ---------------------------------------------------
def merge_chunks(session_id: str):

    session_dir = os.path.join(STORAGE_DIR, session_id)
    os.makedirs(session_dir, exist_ok=True)

    # Fetch manifest from the data plane over HTTP (separate server in production)
    manifest_url = f"{DATA_PLANE_URL}/v1/manifest/{session_id}"
    logger.info("Fetching manifest from %s", manifest_url, extra={"session_id": session_id})
    try:
        req = urllib.request.Request(manifest_url, method="GET")
        req.add_header("User-Agent", "WalrusControlPlane/1.0")
        with urllib.request.urlopen(req) as response:
            manifest = json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        raise Exception(f"manifest missing (data plane returned {e.code})")
    except Exception as e:
        raise Exception(f"Failed to fetch manifest from data plane: {e}")

    chunks = sorted(manifest["chunks"], key=lambda x: x["chunk_index"])

    output = os.path.join(session_dir, "final.mp4")

    with open(output, "wb") as out:
        for c in chunks:
            blob_id = c.get("blob_id")
            if not blob_id:
                raise Exception(f"Missing blob_id for chunk {c.get('chunk_id')}")
            
            # Fetch raw bytes from Walrus Aggregator
            blob_data = read_blob(blob_id)
            out.write(blob_data)

    return output


# ---------------------------------------------------
# ASYNC UPLOAD PROCESSING
# ---------------------------------------------------
def process_upload_task(session_id: str, owner: str, title: Optional[str] = None, is_public: bool = True):
    try:
        UPLOAD_STATUS[session_id] = {"status": "merging chunks (waiting for walrus sync)"}
        merged = merge_chunks(session_id)
        logger.info("Merged chunks", extra={"session_id": session_id})
        
        # New: Server-side validation
        try:
            UPLOAD_STATUS[session_id]["status"] = "validating file"
            meta = validate_video_assets(merged)
            logger.info("Validation passed", extra={"session_id": session_id, "meta": meta})
        except Exception as ve:
            logger.error("Validation failed: %s", ve, extra={"session_id": session_id})
            UPLOAD_STATUS[session_id] = {"status": "failed", "error": str(ve)}
            if os.path.exists(merged): os.unlink(merged)
            return

        checksum = file_checksum(merged)

        existing = get_video_by_checksum(checksum)
        if existing:
            # If a new title is provided, update the existing record
            if title and (not existing.get("title") or existing.get("title") != title):
                logger.info("Updating existing video title", extra={"video_id": existing["video_id"], "new_title": title})
                update_video(existing["video_id"], title=title)
            
            UPLOAD_STATUS[session_id] = {
                "status": "upload completed",
                "video_id": existing["video_id"],
                "playlist": f"/hls/{existing['video_id']}/playlist.m3u8"
            }
            return

        video_id = str(uuid.uuid4())
        UPLOAD_STATUS[session_id]["video_id"] = video_id
        
        # Seal-based Encryption: Generate key for private videos
        encryption_key = None
        if not is_public:
            from utils.crypto import generate_key
            encryption_key = generate_key()
            logger.info("Generated encryption key for private video", extra={"video_id": video_id})

        UPLOAD_STATUS[session_id]["status"] = "transcoding to HLS"

        final_mp4 = os.path.join(UPLOAD_DIR, f"{video_id}.mp4")
        os.rename(merged, final_mp4)

        convert_to_hls(final_mp4, video_id)
        
        hls_dir = os.path.join(HLS_DIR, video_id)
        
        # Extract thumbnail
        UPLOAD_STATUS[session_id]["status"] = "extracting thumbnail"
        generate_thumbnail(final_mp4, hls_dir, video_id)

        # Upload all HLS files and the thumbnail to Walrus and record in manifest
        UPLOAD_STATUS[session_id]["status"] = "uploading HLS assets to walrus"
        hls_assets = {} # relative_path -> blob_id
        
        # Collect all files to upload
        to_upload = []
        for root, dirs, files in os.walk(hls_dir):
            for file in files:
                if file == "manifest.json":
                    continue
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, hls_dir)
                to_upload.append((full_path, rel_path))

        logger.info("Uploading %d HLS assets to Walrus", len(to_upload), extra={"video_id": video_id})
        
        from concurrent.futures import ThreadPoolExecutor

        # Apply retries to the store_blob call within the upload task
        @with_retries(max_retries=5, initial_backoff=2)
        def store_blob_with_retries(data: bytes) -> str:
            return store_blob(data)

        def upload_task(paths):
            f_path, r_path = paths
            with open(f_path, "rb") as f:
                data = f.read()
            
            # Encrypt if we have an encryption key
            if encryption_key:
                from utils.crypto import encrypt_data
                data = encrypt_data(data, encryption_key)

            return r_path, store_blob_with_retries(data)

        with ThreadPoolExecutor(max_workers=4) as executor:
            # Use list() to consume the iterator and wait for completion
            results = list(executor.map(upload_task, to_upload))

        for rel_path, blob_id in results:
            hls_assets[rel_path] = blob_id

        # Load the session manifest and enrich it
        session_dir = os.path.join(STORAGE_DIR, session_id)
        session_manifest_path = os.path.join(session_dir, "manifest.json")
        if os.path.exists(session_manifest_path):
            with open(session_manifest_path, "r") as f:
                manifest = json.load(f)
        else:
            # Fallback if manifest was moved or missing
            manifest = {"chunks": [], "video_id": video_id}
            
        manifest["hls_assets"] = hls_assets
        
        UPLOAD_STATUS[session_id]["status"] = "extracting metadata"

        # Save enriched manifest to final HLS location
        final_manifest_path = os.path.join(hls_dir, "manifest.json")
        with open(final_manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)

        # Probe video metadata (duration, resolution, file size)
        meta = probe_video_metadata(final_mp4)

        create_video(
            video_id=video_id,
            owner=owner,
            file_path=final_mp4,
            checksum=checksum,
            title=title,
            duration_seconds=meta.get("duration_seconds"),
            resolution=meta.get("resolution"),
            file_size=meta.get("file_size"),
            is_public=is_public,
            encryption_key=encryption_key,
        )

        # Log ingress usage
        from control_plane.db import log_usage
        log_usage(video_id, owner, "ingress", meta.get("file_size") or 0)
        
        # ---------------------------------------------------
        # PREPARE ON-CHAIN REGISTRATION PARAMS
        # ---------------------------------------------------
        from utils.sui import PACKAGE_ID, REGISTRY_ID
        logger.info("Upload complete — preparing for client-side signature", extra={"video_id": video_id})

        # Fire webhook event
        fire_event("upload.completed", {
            "video_id": video_id,
            "owner": owner,
            "title": title,
            "duration_seconds": meta.get("duration_seconds"),
            "resolution": meta.get("resolution"),
            "file_size": meta.get("file_size"),
            "playlist": f"/hls/{video_id}/playlist.m3u8",
        })

        UPLOAD_STATUS[session_id] = {
            "status": "upload completed",
            "video_id": video_id,
            "playlist": f"/hls/{video_id}/playlist.m3u8",
            "sui_package_id": PACKAGE_ID,
            "sui_registry_id": REGISTRY_ID
        }

    except Exception as e:
        import traceback
        logger.error("Async upload job failed: %s", e, extra={"session_id": session_id})
        traceback.print_exc()
        UPLOAD_STATUS[session_id] = {
            "status": "failed",
            "error": str(e)
        }

# ---------------------------------------------------
# COMPLETE UPLOAD (KICKS OFF ASYNC TASK)
# ---------------------------------------------------
@router.post("/complete-upload/{session_id}")
def complete_upload(
    session_id: str,
    background_tasks: BackgroundTasks,
    title: Optional[str] = None,
    is_public: bool = True,
    owner: str = Depends(get_current_user)
):
    logger.info("Starting async completion", extra={"session_id": session_id})
    UPLOAD_STATUS[session_id] = {"status": "queued"}
    background_tasks.add_task(process_upload_task, session_id, owner, title, is_public)
    return {
        "status": "processing",
        "session_id": session_id,
        "message": "Upload completion scheduled. Poll /v1/upload-status/{session_id} for updates."
    }

# ---------------------------------------------------
# UPLOAD STATUS POLLING
# ---------------------------------------------------
@router.get("/upload-status/{session_id}")
def get_upload_status(session_id: str):
    status = UPLOAD_STATUS.get(session_id)
    if not status:
        raise HTTPException(status_code=404, detail="Session not found or expired")
    return status


# ---------------------------------------------------
# HLS MANIFEST (for data plane to fetch over HTTP)
# ---------------------------------------------------
@router.get("/hls-manifest/{video_id}")
def hls_manifest(video_id: str):
    manifest_path = os.path.join(HLS_DIR, video_id, "manifest.json")
    if not os.path.exists(manifest_path):
        raise HTTPException(status_code=404, detail="HLS manifest not found")
    with open(manifest_path, "r") as f:
        return json.load(f)


# ---------------------------------------------------
# LIST VIDEOS
# ---------------------------------------------------
@router.get("/videos")
def videos(owner: Optional[str] = None):
    return {"videos": list_videos(owner=owner)}


# ---------------------------------------------------
# GET SINGLE VIDEO
# ---------------------------------------------------
@router.get("/videos/{video_id}")
def get_single_video(video_id: str):
    video = get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return video


# ---------------------------------------------------
# UPDATE VIDEO METADATA
# ---------------------------------------------------
class VideoUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    is_public: Optional[bool] = None

@router.patch("/videos/{video_id}")
def patch_video(video_id: str, body: VideoUpdate, owner: str = Depends(get_current_user)):
    video = get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    if video.get("owner") != owner:
        raise HTTPException(status_code=403, detail="Not authorized to update this video")

    updated = update_video(video_id, **body.model_dump(exclude_none=True))
    if not updated:
        raise HTTPException(status_code=400, detail="No fields to update")
    return get_video(video_id)


# ---------------------------------------------------
# DELETE VIDEO
# ---------------------------------------------------
@router.delete("/videos/{video_id}")
def video_delete(video_id: str, owner: str = Depends(get_current_user)):
    video = get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    if video.get("owner") != owner:
        raise HTTPException(status_code=403, detail="Not authorized to delete this video")
    
    # 1. Delete from database
    delete_video(video_id)
    
    # 2. Cleanup local files (HLS segments, thumbnails, etc.)
    # We do this as a courtesy to save disk space
    hls_path = os.path.join(HLS_DIR, video_id)
    if os.path.exists(hls_path):
        shutil.rmtree(hls_path)
        
    mp4_path = os.path.join(UPLOAD_DIR, f"{video_id}.mp4")
    if os.path.exists(mp4_path):
        os.remove(mp4_path)
    
    logger.info("Deleted video and local assets", extra={"video_id": video_id, "owner": owner})
    
    return {"status": "deleted", "video_id": video_id}


# ---------------------------------------------------
# SIGNED PLAYBACK URL
# ---------------------------------------------------
@router.get("/playback-url/{video_id}")
def playback(video_id: str, user_address: str = None):

    video = get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    # ---------------------------------------------------
    # ON-CHAIN PERMISSION CHECK (HARD GATE)
    # Only enforced if the video is NOT public
    # ---------------------------------------------------
    if not video.get("is_public", True):
        if not user_address:
             raise HTTPException(status_code=401, detail="This is a private video. user_address is required for playback authorization")

        # Fast-path: the video owner is always authorized (matches smart contract logic)
        video_owner = video.get("owner", "")
        if video_owner and user_address.lower() == video_owner.lower():
            logger.info("Owner match from DB — granting playback", extra={"user_address": user_address, "video_id": video_id})
        else:
            # Non-owner: fall back to on-chain Sui permission check
            logger.info("Checking SUI permission", extra={"user_address": user_address, "video_id": video_id})
            authorized = check_sui_auth(video_id, user_address)
        
            if not authorized:
                logger.warning("No on-chain policy — blocking playback", extra={"user_address": user_address, "video_id": video_id})
                raise HTTPException(status_code=403, detail="Not authorized to view this video")
            
            logger.info("On-chain permission verified", extra={"user_address": user_address})
    else:
        logger.debug("Video is public — bypassing auth", extra={"video_id": video_id})

    encryption_key = video.get("encryption_key")
    signed = create_signed_url(video_id, "playlist.m3u8", encryption_key=encryption_key)

    # Fire webhook event
    fire_event("playback.requested", {
        "video_id": video_id,
        "user_address": user_address,
    })

    return {
        "video_id": video_id,
        "playlist": signed
    }

# ---------------------------------------------------
# GET THUMBNAIL URL / PROXY
# ---------------------------------------------------
from fastapi.responses import Response

@router.get("/thumbnail/{video_id}")
def get_thumbnail(video_id: str):
    video = get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    # The manifest contains the blob ID for the thumbnail
    # Fetch from Walrus aggregator
    try:
        manifest_url = f"{DATA_PLANE}/v1/manifest/{video_id}"
        resp = requests.get(manifest_url)
        if not resp.ok:
            # Fallback if manifest is not exposed on data plane yet
            raise Exception("Manifest not available")
        manifest = resp.json()
        
        blob_id = manifest.get("hls_assets", {}).get("thumbnail.jpg")
        if not blob_id:
            # If no thumbnail was generated, return 404
            raise HTTPException(status_code=404, detail="Thumbnail not found for this video")
            
        # Proxy the blob from the aggregator
        blob_url = f"{AGGREGATOR}/v1/{blob_id}"
        blob_resp = requests.get(blob_url, stream=True)
        if not blob_resp.ok:
            raise Exception(f"Failed to read from Walrus: {blob_resp.status_code}")
            
        return Response(content=blob_resp.content, media_type="image/jpeg")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error proxying thumbnail: %s", e, extra={"video_id": video_id})
        # Could return a default placeholder here
        raise HTTPException(status_code=500, detail="Could not load thumbnail")