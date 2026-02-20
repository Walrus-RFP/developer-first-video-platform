import os
import json

STORAGE_DIR = "storage"

def get_video_path(video_id):
    # lookup DB later
    # for now assume session_id == video_id
    session_dir = os.path.join(STORAGE_DIR, video_id)
    manifest_path = os.path.join(session_dir, "manifest.json")

    if not os.path.exists(manifest_path):
        raise Exception("Manifest not found")

    with open(manifest_path) as f:
        manifest = json.load(f)

    chunks = sorted(manifest["chunks"], key=lambda c: c["chunk_index"])

    paths = [os.path.join(session_dir, c["chunk_id"]) for c in chunks]
    return paths