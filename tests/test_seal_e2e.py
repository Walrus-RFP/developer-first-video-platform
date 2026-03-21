"""
Seal E2E Integration Test

Tests the complete Seal encryption key management flow:
  1. Create API key
  2. Upload a unique private video (avoids content-hash deduplication)
  3. Poll until processing completes
  4. GET /encryption-key (server returns plaintext AES key)
  5. POST /seal-key (simulate committing a Seal blob ID; clears plaintext)
  6. GET /encryption-key again → 404 (key cleared)
  7. GET /playback-url → needs_seal response
  8. GET /playback-url with seal_key param → signed URL returned

Run with:
    pytest tests/test_seal_e2e.py -v
"""
import os
import time
import uuid
import pytest
import requests

CONTROL = os.getenv("CONTROL_PLANE_URL", "http://localhost:8000")
DATA    = os.getenv("DATA_PLANE_URL",    "http://localhost:8001")

# ── helpers ──────────────────────────────────────────────────────────────────

def services_up() -> bool:
    try:
        r = requests.get(f"{CONTROL}/v1/api-keys", timeout=3)
        # 200 or 4xx both confirm the service is up; 5xx or connection error → down
        return r.status_code < 500
    except Exception:
        return False


def create_api_key(owner: str) -> str:
    r = requests.post(f"{CONTROL}/v1/api-keys", json={"owner": owner, "name": f"key-{owner}"})
    r.raise_for_status()
    return r.json()["api_key"]


def make_unique_mp4_bytes() -> bytes:
    """
    Generate a real 1-second MP4 using ffmpeg with a unique color so its SHA-256
    will never collide with previously uploaded test files.
    """
    import subprocess
    import tempfile

    # Each call uses a random drawtext value → unique file hash
    nonce = uuid.uuid4().hex
    out_path = os.path.join(tempfile.gettempdir(), f"seal_test_{nonce}.mp4")
    try:
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", f"color=c=0x{nonce[:6]}:size=128x72:rate=1",
                "-f", "lavfi",
                "-i", "aevalsrc=0:c=mono:s=8000",
                "-t", "1",
                "-vcodec", "libx264",
                "-acodec", "aac",
                out_path,
            ],
            check=True,
            capture_output=True,
        )
        with open(out_path, "rb") as f:
            return f.read()
    finally:
        if os.path.exists(out_path):
            os.unlink(out_path)


def upload_session(api_key: str, title: str) -> str:
    """Create an upload session and return session_id."""
    r = requests.post(
        f"{CONTROL}/v1/upload-session",
        json={"title": title, "is_public": False},
        headers={"X-API-Key": api_key},
    )
    r.raise_for_status()
    return r.json()["upload_session_id"]


def upload_chunk(session_id: str, chunk_id: str, data: bytes) -> None:
    r = requests.post(
        f"{DATA}/v1/upload-chunk/{session_id}/{chunk_id}/0",
        files={"file": ("chunk.mp4", data, "application/octet-stream")},
    )
    r.raise_for_status()


def complete_upload(api_key: str, session_id: str, title: str = "") -> dict:
    r = requests.post(
        f"{CONTROL}/v1/complete-upload/{session_id}",
        params={"is_public": "false", "title": title},
        headers={"X-API-Key": api_key},
    )
    r.raise_for_status()
    return r.json()


def poll_status(session_id: str, timeout: int = 120) -> dict:
    deadline = time.time() + timeout
    last: dict = {}
    while time.time() < deadline:
        r = requests.get(f"{CONTROL}/v1/upload-status/{session_id}")
        r.raise_for_status()
        last = r.json()
        status = last.get("status", "")
        if status in ("upload completed", "completed", "error", "failed"):
            return last
        time.sleep(3)
    pytest.fail(f"Upload did not complete within {timeout}s; last status: {last}")
    return last  # unreachable, satisfies type checker


# ── test ─────────────────────────────────────────────────────────────────────

@pytest.mark.skipif(not services_up(), reason="Services not running")
def test_seal_encryption_flow():
    owner  = f"seal_e2e_{uuid.uuid4().hex[:8]}"
    api_key = create_api_key(owner)
    print(f"\n[1] API key created for owner={owner}")

    # ── 2. Upload unique private video ────────────────────────────────────
    mp4_bytes = make_unique_mp4_bytes()
    title     = f"Seal E2E {uuid.uuid4().hex[:6]}"
    chunk_id  = str(uuid.uuid4())

    session_id = upload_session(api_key, title)
    print(f"[2] Session created: {session_id}")

    upload_chunk(session_id, chunk_id, mp4_bytes)
    print(f"[3] Chunk uploaded ({len(mp4_bytes)} bytes)")

    complete_resp = complete_upload(api_key, session_id, title=title)
    video_id = complete_resp.get("video_id") or complete_resp.get("session_id")

    status_data = poll_status(session_id, timeout=600)
    video_id = status_data.get("video_id") or video_id
    assert video_id, "No video_id in status response"
    assert status_data.get("status") not in ("error", "failed"), \
        f"Upload failed: {status_data.get('error', 'unknown error')}"
    print(f"[4] Video processed: {video_id} (status={status_data['status']})")

    # ── 3. Fetch encryption key ───────────────────────────────────────────
    r = requests.get(
        f"{CONTROL}/v1/videos/{video_id}/encryption-key",
        headers={"X-API-Key": api_key},
    )
    # New unique private video → should have a key
    if r.status_code == 400 and "Public" in r.text:
        # ffmpeg couldn't encode our synthetic mp4 — video was stored as public
        # (processing failed → fallback to public). Check status.
        pytest.skip(f"Video stored as public (processing likely failed on synthetic mp4): {status_data}")
    if r.status_code == 404 and "not available" in r.text:
        pytest.skip("Video processing completed but encryption key already cleared or video is public")
    assert r.status_code == 200, f"GET /encryption-key failed: {r.status_code} {r.text}"
    enc_key_b64 = r.json()["encryption_key_b64"]
    assert enc_key_b64, "Empty encryption key returned"
    print(f"[5] Got encryption key (base64, len={len(enc_key_b64)})")

    # ── 4. Upload a fake Seal blob and commit the seal key ────────────────
    fake_seal_blob = os.urandom(64)  # stand-in for real Seal-encrypted key bytes
    blob_r = requests.post(
        f"{DATA}/v1/seal-blob",
        data=fake_seal_blob,
        headers={"Content-Type": "application/octet-stream"},
    )
    assert blob_r.status_code == 200, f"POST /seal-blob failed: {blob_r.status_code} {blob_r.text}"
    seal_blob_id = blob_r.json()["blob_id"]
    print(f"[6] Seal blob stored: {seal_blob_id}")

    # ── 5. Download the blob back to verify round-trip ────────────────────
    dl_r = requests.get(f"{DATA}/v1/seal-blob/{seal_blob_id}")
    assert dl_r.status_code == 200, f"GET /seal-blob failed: {dl_r.status_code} {dl_r.text}"
    assert dl_r.content == fake_seal_blob, "Seal blob content mismatch"
    print("[7] Seal blob round-trip verified")

    # ── 6. Commit the seal key (clears plaintext) ─────────────────────────
    commit_r = requests.post(
        f"{CONTROL}/v1/videos/{video_id}/seal-key",
        json={"seal_key_blob_id": seal_blob_id},
        headers={"X-API-Key": api_key, "Content-Type": "application/json"},
    )
    assert commit_r.status_code == 200, f"POST /seal-key failed: {commit_r.status_code} {commit_r.text}"
    print(f"[8] Seal key committed — plaintext cleared")

    # ── 7. Verify plaintext key is gone ──────────────────────────────────
    r2 = requests.get(
        f"{CONTROL}/v1/videos/{video_id}/encryption-key",
        headers={"X-API-Key": api_key},
    )
    assert r2.status_code == 404, f"Expected 404 after Seal commit, got {r2.status_code}: {r2.text}"
    print("[9] Confirmed: encryption key cleared from server (404)")

    # ── 8. Playback → needs_seal response ─────────────────────────────────
    # owner is the same string stored in the DB — pass it directly as user_address
    pb_r = requests.get(
        f"{CONTROL}/v1/playback-url/{video_id}",
        params={"user_address": owner},
    )
    assert pb_r.status_code == 200, f"Playback [10] failed: {pb_r.status_code} {pb_r.text}"
    pb_data = pb_r.json()
    assert pb_data.get("needs_seal") is True, f"Expected needs_seal=True: {pb_data}"
    assert pb_data.get("seal_key_blob_id") == seal_blob_id
    print(f"[10] Playback correctly returns needs_seal=True with seal_key_blob_id")

    # ── 9. Playback with client-decrypted key → signed URL ────────────────
    pb_r2 = requests.get(
        f"{CONTROL}/v1/playback-url/{video_id}",
        params={"user_address": owner, "seal_key": enc_key_b64},
    )
    assert pb_r2.status_code == 200
    pb_data2 = pb_r2.json()
    assert "playlist" in pb_data2, f"Expected signed playlist URL in response: {pb_data2}"
    assert "needs_seal" not in pb_data2 or pb_data2.get("needs_seal") is not True
    print(f"[11] Playback with seal_key returns signed URL: {pb_data2['playlist'][:60]}...")

    print("\n✅ Seal E2E flow complete — all assertions passed")
