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
import urllib.parse
from typing import Optional
from pydantic import BaseModel
from utils.walrus import read_blob, store_blob, with_retries

# Server-side Validation Constants
MAX_VIDEO_SIZE_MB = 1000  # 1GB limit
ALLOWED_VIDEO_CODECS = {"h264", "hevc", "vp9", "av1"}
ALLOWED_AUDIO_CODECS = {"aac", "mp3", "opus", "vorbis"}

from typing import List
from control_plane.db import (
    create_video,
    list_videos,
    get_video,
    get_video_by_checksum,
    update_video,
    delete_video,
    set_upload_status,
    get_upload_status,
    get_video_analytics,
    store_seal_key,
    get_encryption_key,
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
AGGREGATOR = os.getenv("WALRUS_AGGREGATOR", "https://aggregator.walrus-testnet.walrus.space")
PUBLISHER = os.getenv("WALRUS_PUBLISHER", "https://publisher.walrus-testnet.walrus.space")

# HLS assets stored with enough epochs to last ~1 year on testnet
HLS_EPOCHS = int(os.getenv("WALRUS_HLS_EPOCHS", "200"))

os.makedirs(STORAGE_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(HLS_DIR, exist_ok=True)


# ---------------------------------------------------
# CREATE UPLOAD SESSION
# ---------------------------------------------------
@router.post("/upload-session")
def create_upload_session(owner: str = Depends(get_current_user)):
    session_id = str(uuid.uuid4())
    session_dir = os.path.join(STORAGE_DIR, session_id)
    os.makedirs(session_dir, exist_ok=True)
    set_upload_status(session_id, "created", owner=owner)
    return {
        "upload_session_id": session_id,
        "upload_path": session_dir
    }


# ---------------------------------------------------
# CHECKSUM
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

    variants = [
        {"name": "1080p", "w": 1920, "h": 1080, "b": "5000k"},
        {"name": "720p",  "w": 1280, "h": 720,  "b": "2800k"},
        {"name": "480p",  "w": 854,  "h": 480,  "b": "1400k"},
    ]

    master_playlist_content = "#EXTM3U\n#EXT-X-VERSION:3\n"

    for v in variants:
        variant_dir = os.path.join(output_dir, v["name"])
        os.makedirs(variant_dir, exist_ok=True)
        variant_playlist = os.path.join(variant_dir, "index.m3u8")

        cmd = [
            FFMPEG, "-nostdin",
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

        logger.info("Generating %s variant", v["name"], extra={"video_id": video_id})
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            logger.error("FFmpeg error: %s", res.stderr, extra={"video_id": video_id})
            res.check_returncode()

        bandwidth = int(v["b"].replace("k", "000")) + 128000
        master_playlist_content += f"#EXT-X-STREAM-INF:BANDWIDTH={bandwidth},RESOLUTION={v['w']}x{v['h']}\n"
        master_playlist_content += f"{v['name']}/index.m3u8\n"

    master_path = os.path.join(output_dir, "playlist.m3u8")
    with open(master_path, "w") as f:
        f.write(master_playlist_content)

    return master_path


# ---------------------------------------------------
# THUMBNAIL GENERATION
# ---------------------------------------------------
def generate_thumbnail(input_path: str, output_dir: str, video_id: str):
    FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
    thumb_path = os.path.join(output_dir, "thumbnail.jpg")

    cmd = [
        FFMPEG, "-y", "-nostdin",
        "-i", input_path,
        "-ss", "00:00:01.000",
        "-vframes", "1",
        "-vf", "scale=1280:-2",
        "-q:v", "2",
        thumb_path,
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
# PROBE VIDEO METADATA
# ---------------------------------------------------
def probe_video_metadata(file_path: str) -> dict:
    result = {
        "duration_seconds": None,
        "resolution": None,
        "file_size": None,
        "video_codec": None,
        "audio_codec": None,
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
        file_path,
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
    meta = probe_video_metadata(file_path)

    size_mb = (meta["file_size"] or 0) / (1024 * 1024)
    if size_mb > MAX_VIDEO_SIZE_MB:
        raise ValueError(f"Video file too large: {size_mb:.1f}MB (Max: {MAX_VIDEO_SIZE_MB}MB)")

    if not meta["video_codec"]:
        raise ValueError("Invalid video file: No video stream detected or file is corrupted")

    if meta["video_codec"] not in ALLOWED_VIDEO_CODECS:
        logger.warning("Unsupported video codec: %s", meta["video_codec"])

    return meta


# ---------------------------------------------------
# MERGE CHUNKS
# ---------------------------------------------------
def merge_chunks(session_id: str):

    session_dir = os.path.join(STORAGE_DIR, session_id)
    os.makedirs(session_dir, exist_ok=True)

    manifest_url = f"{DATA_PLANE}/v1/manifest/{session_id}"
    logger.info("Fetching manifest from %s", manifest_url, extra={"session_id": session_id})
    try:
        req = urllib.request.Request(manifest_url, method="GET")
        req.add_header("User-Agent", "WalStream-ControlPlane/1.0")
        with urllib.request.urlopen(req, timeout=10) as response:
            manifest = json.loads(response.read().decode("utf-8"))
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
            blob_data = read_blob(blob_id)
            expected_checksum = c.get("checksum")
            if expected_checksum:
                actual_checksum = hashlib.sha256(blob_data).hexdigest()
                if actual_checksum != expected_checksum:
                    raise Exception(
                        f"Chunk integrity failure for {c.get('chunk_id')}: "
                        f"expected {expected_checksum}, got {actual_checksum}"
                    )
            out.write(blob_data)

    return output


# ---------------------------------------------------
# ASYNC UPLOAD PROCESSING
# ---------------------------------------------------
def process_upload_task(session_id: str, owner: str, title: Optional[str] = None, is_public: bool = True, description: Optional[str] = None, tags: Optional[List[str]] = None):
    try:
        set_upload_status(session_id, "merging chunks (waiting for walrus sync)", owner=owner)
        fire_event("upload.processing", {"session_id": session_id, "owner": owner, "stage": "merging_chunks"})
        merged = merge_chunks(session_id)
        logger.info("Merged chunks", extra={"session_id": session_id})

        try:
            set_upload_status(session_id, "validating file", owner=owner)
            meta = validate_video_assets(merged)
            logger.info("Validation passed", extra={"session_id": session_id, "meta": meta})
        except Exception as ve:
            logger.error("Validation failed: %s", ve, extra={"session_id": session_id})
            set_upload_status(session_id, "failed", error=str(ve), owner=owner)
            if os.path.exists(merged):
                os.unlink(merged)
            return

        checksum = file_checksum(merged)

        existing = get_video_by_checksum(checksum)
        if existing:
            if title and (not existing.get("title") or existing.get("title") != title):
                update_video(existing["video_id"], title=title)

            enc_key = existing.get("encryption_key")
            signed_url = create_signed_url(existing["video_id"], "playlist.m3u8", encryption_key=enc_key)
            set_upload_status(
                session_id, "upload completed",
                video_id=existing["video_id"],
                playlist=signed_url,
                owner=owner,
            )
            return

        video_id = str(uuid.uuid4())

        encryption_key = None
        if not is_public:
            from utils.crypto import generate_key
            encryption_key = generate_key()
            logger.info("Generated encryption key for private video", extra={"video_id": video_id})

        set_upload_status(session_id, "transcoding to HLS", video_id=video_id, owner=owner)
        fire_event("upload.processing", {"session_id": session_id, "owner": owner, "stage": "transcoding", "video_id": video_id})

        final_mp4 = os.path.join(UPLOAD_DIR, f"{video_id}.mp4")
        os.rename(merged, final_mp4)

        convert_to_hls(final_mp4, video_id)

        hls_dir = os.path.join(HLS_DIR, video_id)

        set_upload_status(session_id, "extracting thumbnail", video_id=video_id, owner=owner)
        generate_thumbnail(final_mp4, hls_dir, video_id)

        set_upload_status(session_id, "uploading HLS assets to walrus", video_id=video_id, owner=owner)
        fire_event("upload.processing", {"session_id": session_id, "owner": owner, "stage": "uploading_to_walrus", "video_id": video_id})
        hls_assets = {}

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

        @with_retries(max_retries=5, initial_backoff=2)
        def store_blob_with_retries(data: bytes) -> str:
            return store_blob(data, epochs=HLS_EPOCHS)

        def upload_task(paths):
            f_path, r_path = paths
            with open(f_path, "rb") as f:
                data = f.read()

            if encryption_key:
                from utils.crypto import encrypt_data
                data = encrypt_data(data, encryption_key)

            return r_path, store_blob_with_retries(data)

        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(upload_task, to_upload))

        for rel_path, blob_id in results:
            hls_assets[rel_path] = blob_id

        # Load the session manifest and enrich it with HLS asset blob IDs
        session_dir = os.path.join(STORAGE_DIR, session_id)
        session_manifest_path = os.path.join(session_dir, "manifest.json")
        if os.path.exists(session_manifest_path):
            with open(session_manifest_path, "r") as f:
                manifest = json.load(f)
        else:
            manifest = {"chunks": [], "video_id": video_id}

        manifest["hls_assets"] = hls_assets

        set_upload_status(session_id, "extracting metadata", video_id=video_id, owner=owner)

        final_manifest_path = os.path.join(hls_dir, "manifest.json")
        with open(final_manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)

        meta = probe_video_metadata(final_mp4)

        create_video(
            video_id=video_id,
            owner=owner,
            file_path=final_mp4,
            checksum=checksum,
            title=title,
            description=description,
            tags=tags,
            duration_seconds=meta.get("duration_seconds"),
            resolution=meta.get("resolution"),
            file_size=meta.get("file_size"),
            is_public=is_public,
            encryption_key=encryption_key,
            content_hash=checksum,
        )

        from control_plane.db import log_usage
        log_usage(video_id, owner, "ingress", meta.get("file_size") or 0)

        from utils.sui import PACKAGE_ID, REGISTRY_ID
        logger.info("Upload complete — preparing for client-side signature", extra={"video_id": video_id})

        fire_event("upload.completed", {
            "video_id": video_id,
            "owner": owner,
            "title": title,
            "duration_seconds": meta.get("duration_seconds"),
            "resolution": meta.get("resolution"),
            "file_size": meta.get("file_size"),
            "playlist": f"/hls/{video_id}/playlist.m3u8",
        })

        set_upload_status(
            session_id, "upload completed",
            video_id=video_id,
            playlist=f"/hls/{video_id}/playlist.m3u8",
            sui_package_id=PACKAGE_ID,
            sui_registry_id=REGISTRY_ID,
            owner=owner,
            content_hash=checksum,
        )

        # Clean up temporary session directory
        session_dir = os.path.join(STORAGE_DIR, session_id)
        if os.path.exists(session_dir):
            shutil.rmtree(session_dir, ignore_errors=True)

    except Exception as e:
        import traceback
        logger.error("Async upload job failed: %s", e, extra={"session_id": session_id})
        traceback.print_exc()
        set_upload_status(session_id, "failed", error=str(e), owner=owner)
        fire_event("upload.failed", {"session_id": session_id, "owner": owner, "error": str(e)})


# ---------------------------------------------------
# VIDEO VERSIONING
# ---------------------------------------------------
class VideoVersionCreate(BaseModel):
    parent_video_id: str
    title: Optional[str] = None
    description: Optional[str] = None
    is_public: bool = True

@router.post("/videos/{video_id}/version")
def create_video_version(
    video_id: str,
    body: VideoVersionCreate,
    owner: str = Depends(get_current_user),
):
    """
    Register a new version of an existing video.
    Creates a DB record inheriting the parent's assets, then returns the
    Sui transaction parameters for the client to sign
    (video_registry::register_video_version on-chain).
    """
    parent = get_video(body.parent_video_id)
    if not parent:
        raise HTTPException(status_code=404, detail="Parent video not found")
    if parent.get("owner") != owner:
        raise HTTPException(status_code=403, detail="Not authorized: you do not own the parent video")

    new_version = (parent.get("version") or 1) + 1

    create_video(
        video_id=video_id,
        owner=owner,
        file_path=parent.get("file_path", ""),
        checksum=parent.get("checksum", ""),
        title=body.title or parent.get("title"),
        description=body.description or parent.get("description"),
        duration_seconds=parent.get("duration_seconds"),
        resolution=parent.get("resolution"),
        file_size=parent.get("file_size"),
        is_public=body.is_public,
        encryption_key=parent.get("encryption_key"),
        content_hash=parent.get("content_hash"),
    )

    from sqlalchemy import text as _text
    from control_plane.db import engine as _engine
    with _engine.begin() as conn:
        conn.execute(_text("UPDATE videos SET version = :v WHERE video_id = :vid"),
                     {"v": new_version, "vid": video_id})

    from utils.sui import PACKAGE_ID, REGISTRY_ID
    fire_event("video.versioned", {
        "video_id": video_id,
        "parent_video_id": body.parent_video_id,
        "owner": owner,
        "version": new_version,
    })

    return {
        "video_id": video_id,
        "parent_video_id": body.parent_video_id,
        "version": new_version,
        "sui_package_id": PACKAGE_ID,
        "sui_registry_id": REGISTRY_ID,
        "sui_call": "register_video_version",
        "message": "Sign the Sui transaction to register this version on-chain.",
    }


# ---------------------------------------------------
# SEAL KEY MANAGEMENT
# ---------------------------------------------------

@router.get("/videos/{video_id}/encryption-key")
def reveal_encryption_key(video_id: str, owner: str = Depends(get_current_user)):
    """
    One-time endpoint: returns the plaintext AES-GCM key so the video owner
    can Seal-encrypt it client-side and commit the blob ID via POST seal-key.
    Returns 404 once the key has been cleared (Seal setup already completed).
    """
    video = get_video(video_id)
    if not video:
        raise HTTPException(404, "Video not found")
    if video.get("owner") != owner:
        raise HTTPException(403, "Not authorized")
    if video.get("is_public", True):
        raise HTTPException(400, "Public videos are not encrypted")

    key = get_encryption_key(video_id)
    if not key:
        raise HTTPException(404, "Encryption key not available — Seal setup may already be complete")
    return {"video_id": video_id, "encryption_key_b64": key}


class SealKeyCommit(BaseModel):
    seal_key_blob_id: str

@router.post("/videos/{video_id}/seal-key")
def commit_seal_key(video_id: str, body: SealKeyCommit, owner: str = Depends(get_current_user)):
    """
    Commit the Walrus blob ID of the Seal-encrypted AES key.
    This clears the plaintext key from the server — the server will never
    hold the decryption key again. Viewers must use the Mysten Seal SDK to
    recover the key via on-chain access verification.
    """
    video = get_video(video_id)
    if not video:
        raise HTTPException(404, "Video not found")
    if video.get("owner") != owner:
        raise HTTPException(403, "Not authorized")

    store_seal_key(video_id, body.seal_key_blob_id)
    fire_event("video.seal_key_committed", {
        "video_id": video_id,
        "seal_key_blob_id": body.seal_key_blob_id,
        "owner": owner,
    })
    logger.info("Seal key committed — plaintext key cleared from server",
                extra={"video_id": video_id, "seal_key_blob_id": body.seal_key_blob_id})
    return {
        "video_id": video_id,
        "seal_key_blob_id": body.seal_key_blob_id,
        "message": "Seal key committed. Plaintext encryption key has been cleared from the server.",
    }


# ---------------------------------------------------
# COMPLETE UPLOAD (KICKS OFF ASYNC TASK)
# ---------------------------------------------------
@router.post("/complete-upload/{session_id}")
def complete_upload(
    session_id: str,
    background_tasks: BackgroundTasks,
    title: Optional[str] = None,
    description: Optional[str] = None,
    tags: Optional[str] = None,   # comma-separated, e.g. "education,tutorial"
    is_public: bool = True,
    owner: str = Depends(get_current_user)
):
    logger.info("Starting async completion", extra={"session_id": session_id})
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
    set_upload_status(session_id, "queued", owner=owner)
    background_tasks.add_task(process_upload_task, session_id, owner, title, is_public, description, tag_list)
    return {
        "status": "processing",
        "session_id": session_id,
        "message": "Upload completion scheduled. Poll /v1/upload-status/{session_id} for updates.",
    }


# ---------------------------------------------------
# UPLOAD STATUS POLLING
# ---------------------------------------------------
@router.get("/upload-status/{session_id}")
def get_upload_status_endpoint(session_id: str):
    status = get_upload_status(session_id)
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
def videos(owner: Optional[str] = None, search: Optional[str] = None, tag: Optional[str] = None):
    return {"videos": list_videos(owner=owner, search=search, tag=tag)}


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
    tags: Optional[List[str]] = None
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

    delete_video(video_id)

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
def playback(video_id: str, user_address: Optional[str] = None, seal_key: Optional[str] = None):
    video = get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    if not video.get("is_public", True):
        if not user_address:
            raise HTTPException(
                status_code=401,
                detail="This is a private video. user_address is required for playback authorization",
            )

        video_owner = video.get("owner", "")
        if video_owner and user_address.lower() == video_owner.lower():
            logger.info("Owner match from DB — granting playback",
                        extra={"user_address": user_address, "video_id": video_id})
        else:
            logger.info("Checking SUI permission",
                        extra={"user_address": user_address, "video_id": video_id})
            authorized = check_sui_auth(video_id, user_address)

            if not authorized:
                logger.warning("No on-chain policy — blocking playback",
                               extra={"user_address": user_address, "video_id": video_id})
                raise HTTPException(status_code=403, detail="Not authorized to view this video")

            logger.info("On-chain permission verified", extra={"user_address": user_address})
    else:
        logger.debug("Video is public — bypassing auth", extra={"video_id": video_id})

    seal_key_blob_id = video.get("seal_key_blob_id")

    # Seal-encrypted video: client must decrypt the key via Seal SDK first
    if seal_key_blob_id and not seal_key:
        return {
            "needs_seal": True,
            "video_id": video_id,
            "seal_key_blob_id": seal_key_blob_id,
            "message": (
                "This video uses Mysten Seal key management. "
                "Fetch the seal blob, decrypt with SealClient, "
                "then re-request with &seal_key=<base64_aes_key>."
            ),
        }

    # Use client-provided key (after Seal decryption) or server-stored key
    encryption_key = seal_key if seal_key else video.get("encryption_key")
    signed = create_signed_url(video_id, "playlist.m3u8", encryption_key=encryption_key)

    fire_event("playback.requested", {
        "video_id": video_id,
        "user_address": user_address,
    })

    return {"video_id": video_id, "playlist": signed}


# ---------------------------------------------------
# PER-VIDEO ANALYTICS
# ---------------------------------------------------
@router.get("/videos/{video_id}/analytics")
def video_analytics(video_id: str, owner: str = Depends(get_current_user)):
    video = get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    if video.get("owner") != owner:
        raise HTTPException(status_code=403, detail="Not authorized to view analytics for this video")
    return get_video_analytics(video_id)


# ---------------------------------------------------
# EMBED / SHARE URL
# ---------------------------------------------------
@router.get("/videos/{video_id}/embed")
def video_embed(video_id: str, user_address: Optional[str] = None):
    """
    Returns an embed snippet and a shareable iframe URL for cross-application reuse.
    Public videos are freely embeddable. Private videos require user_address for the signed URL.
    """
    video = get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    if not video.get("is_public", True) and not user_address:
        raise HTTPException(
            status_code=401,
            detail="Private video — provide user_address to generate an embed URL",
        )

    encryption_key = video.get("encryption_key")
    playlist_url = create_signed_url(video_id, "playlist.m3u8", encryption_key=encryption_key)

    embed_url = f"{PUBLIC_DATA_PLANE}/embed/{video_id}?playlist={urllib.parse.quote(playlist_url)}"

    iframe_html = (
        f'<iframe src="{embed_url}" '
        f'width="640" height="360" frameborder="0" allowfullscreen '
        f'title="{video.get("title") or video_id}"></iframe>'
    )

    return {
        "video_id": video_id,
        "playlist_url": playlist_url,
        "embed_url": embed_url,
        "iframe_html": iframe_html,
    }


# ---------------------------------------------------
# THUMBNAIL PROXY
# ---------------------------------------------------
from fastapi.responses import Response

@router.get("/thumbnail/{video_id}")
def get_thumbnail(video_id: str):
    video = get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    # 1. Try local disk first (fastest path)
    local_thumb = os.path.join(HLS_DIR, video_id, "thumbnail.jpg")
    if os.path.exists(local_thumb):
        with open(local_thumb, "rb") as f:
            return Response(content=f.read(), media_type="image/jpeg")

    # 2. Try to get blob_id from local manifest
    manifest_path = os.path.join(HLS_DIR, video_id, "manifest.json")
    blob_id = None

    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r") as f:
                manifest = json.load(f)
            blob_id = manifest.get("hls_assets", {}).get("thumbnail.jpg")
        except Exception:
            pass

    if not blob_id:
        raise HTTPException(status_code=404, detail="Thumbnail not found for this video")

    # 3. Fetch from Walrus aggregator
    try:
        blob_url = f"{AGGREGATOR}/v1/blobs/{blob_id}"
        req = urllib.request.Request(blob_url, method="GET")
        req.add_header("User-Agent", "WalStream/1.0")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read()
        return Response(content=data, media_type="image/jpeg")
    except Exception as e:
        logger.error("Error fetching thumbnail from Walrus: %s", e, extra={"video_id": video_id})
        raise HTTPException(status_code=500, detail="Could not load thumbnail")
