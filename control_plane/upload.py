print("UPLOAD ROUTER LOADED")

from fastapi import APIRouter, HTTPException
import uuid
import os
import json
import hashlib
import shutil
import subprocess
from utils.walrus import read_blob, store_blob, with_retries

from control_plane.db import (
    create_video,
    list_videos,
    get_video,
    get_video_by_checksum,
)

from utils.signing import create_signed_url
from utils.sui import is_authorized as check_sui_auth

router = APIRouter()

STORAGE_DIR = "storage"
UPLOAD_DIR = os.path.join(STORAGE_DIR, "uploads")
HLS_DIR = os.path.join(STORAGE_DIR, "hls")

os.makedirs(STORAGE_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(HLS_DIR, exist_ok=True)


# ---------------------------------------------------
# CREATE UPLOAD SESSION
# ---------------------------------------------------
@router.post("/upload-session")
def create_upload_session():
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

        print(f"Generating {v['name']} variant for {video_id}...")
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            print(f"[FFMPEG ERROR] {res.stderr}")
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
# Merge chunks
# ---------------------------------------------------
def merge_chunks(session_id: str):

    session_dir = os.path.join(STORAGE_DIR, session_id)
    manifest_path = os.path.join(session_dir, "manifest.json")

    if not os.path.exists(manifest_path):
        raise Exception("manifest missing")

    with open(manifest_path) as f:
        manifest = json.load(f)

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
# COMPLETE UPLOAD
# ---------------------------------------------------
from typing import Optional

@router.post("/complete-upload/{session_id}")
def complete_upload(session_id: str, owner: Optional[str] = "test_user"):
    print(f"[COMPLETE] Starting completion for session {session_id} for owner {owner}")
    try:
        merged = merge_chunks(session_id)
        print(f"[COMPLETE] Merged chunks for {session_id}")
        checksum = file_checksum(merged)

        existing = get_video_by_checksum(checksum)
        if existing:
            return {
                "status": "reused existing asset",
                "video_id": existing["video_id"],
                "playlist": f"/hls/{existing['video_id']}/playlist.m3u8"
            }

        video_id = str(uuid.uuid4())

        final_mp4 = os.path.join(UPLOAD_DIR, f"{video_id}.mp4")
        os.rename(merged, final_mp4)

        convert_to_hls(final_mp4, video_id)

        # Upload all HLS files to Walrus and record in manifest
        hls_dir = os.path.join(HLS_DIR, video_id)
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

        print(f"Uploading {len(to_upload)} HLS assets for {video_id} to Walrus (Parallel)...")
        
        from concurrent.futures import ThreadPoolExecutor

        # Apply retries to the store_blob call within the upload task
        @with_retries(max_retries=5, initial_backoff=2)
        def store_blob_with_retries(data: bytes) -> str:
            return store_blob(data)

        def upload_task(paths):
            f_path, r_path = paths
            with open(f_path, "rb") as f:
                data = f.read()
            return r_path, store_blob_with_retries(data)

        with ThreadPoolExecutor(max_workers=1) as executor:
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
        
        # Save enriched manifest to final HLS location
        final_manifest_path = os.path.join(hls_dir, "manifest.json")
        with open(final_manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)

        create_video(
            video_id=video_id,
            owner=owner,
            file_path=final_mp4,
            checksum=checksum,
        )
        
        # ---------------------------------------------------
        # ON-CHAIN REGISTRATION (Optional/Fail-soft)
        # ---------------------------------------------------
        try:
            from utils.sui import PACKAGE_ID, REGISTRY_ID
            print(f"[ON-CHAIN] Registering video {video_id} on Sui...")
            cmd = [
                "sui", "client", "call",
                "--package", PACKAGE_ID,
                "--module", "video_registry",
                "--function", "register_video",
                "--args", REGISTRY_ID, f"string:{video_id}",
                "--gas-budget", "50000000"
            ]
            subprocess.run(cmd, capture_output=True, check=True)
            print(f"[ON-CHAIN] Video {video_id} registered successfully.")
        except Exception as e:
            print(f"[ON-CHAIN WARNING] Registration failed: {e}")
            # We don't fail the whole upload if Sui is down, 
            # but usually for this RFP, we want it to work.
        print(f"[COMPLETE] Success! Generated video_id {video_id}")

        return {
            "status": "upload completed",
            "video_id": video_id,
            "playlist": f"/hls/{video_id}/playlist.m3u8"
        }

    except Exception as e:
        import traceback
        print(f"[COMPLETE] ERROR: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------
# LIST VIDEOS
# ---------------------------------------------------
@router.get("/videos")
def videos(owner: Optional[str] = None):
    return {"videos": list_videos(owner=owner)}


# ---------------------------------------------------
# SIGNED PLAYBACK URL
# ---------------------------------------------------
@router.get("/playback-url/{video_id}")
def playback(video_id: str, user_address: str = None):

    video = get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    # ---------------------------------------------------
    # ON-CHAIN PERMISSION CHECK
    # ---------------------------------------------------
    if user_address:
        print(f"[AUTH] Checking SUI permission for {user_address} on {video_id}...")
        if not check_sui_auth(video_id, user_address):
            print(f"[AUTH] Permission denied for {user_address}")
            raise HTTPException(status_code=403, detail="On-chain permission denied")
        print(f"[AUTH] Permission granted.")

    signed = create_signed_url(video_id, "playlist.m3u8")

    return {
        "video_id": video_id,
        "playlist": signed
    }