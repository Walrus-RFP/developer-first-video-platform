"""
Integration tests for the upload pipeline.
Requires services running:  control-plane :8000, data-plane :8001

Run:  pytest tests/test_upload.py -v
"""
import os
import time
import pytest
import requests

CONTROL = os.getenv("CONTROL_PLANE_URL", "http://localhost:8000")
DATA    = os.getenv("DATA_PLANE_URL",    "http://localhost:8001")
TEST_VIDEO = os.path.join(os.path.dirname(__file__), "assets", "test_video.mp4")


@pytest.fixture(scope="module")
def api_key():
    resp = requests.post(f"{CONTROL}/v1/api-keys", json={"owner": "0xTestSuite", "name": "pytest"})
    assert resp.status_code == 200, f"Failed to create API key: {resp.text}"
    return resp.json()["api_key"]


@pytest.fixture(scope="module")
def session_id(api_key):
    resp = requests.post(f"{CONTROL}/v1/upload-session", headers={"X-API-Key": api_key})
    assert resp.status_code == 200, f"Failed to create session: {resp.text}"
    sid = resp.json()["upload_session_id"]
    assert sid
    return sid


class TestUploadSession:
    def test_create_session(self, api_key):
        resp = requests.post(f"{CONTROL}/v1/upload-session", headers={"X-API-Key": api_key})
        assert resp.status_code == 200
        data = resp.json()
        assert "upload_session_id" in data

    def test_create_session_without_key_fails(self):
        resp = requests.post(f"{CONTROL}/v1/upload-session")
        assert resp.status_code in (401, 403)

    def test_invalid_key_fails(self):
        resp = requests.post(f"{CONTROL}/v1/upload-session", headers={"X-API-Key": "invalid_key"})
        assert resp.status_code in (401, 403)


class TestChunkUpload:
    def test_upload_chunk(self, session_id):
        assert os.path.exists(TEST_VIDEO), f"Test video not found: {TEST_VIDEO}"
        with open(TEST_VIDEO, "rb") as f:
            data = f.read(1024 * 1024)  # first 1MB
        resp = requests.post(
            f"{DATA}/v1/upload-chunk/{session_id}/chunk_0/0",
            files={"file": ("chunk_0", data, "application/octet-stream")},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] in ("chunk stored", "chunk already stored")

    def test_upload_empty_chunk_fails(self, session_id):
        resp = requests.post(
            f"{DATA}/v1/upload-chunk/{session_id}/empty_chunk/99",
            files={"file": ("empty", b"", "application/octet-stream")},
        )
        assert resp.status_code == 400

    def test_get_manifest(self, session_id):
        resp = requests.get(f"{DATA}/v1/manifest/{session_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "chunks" in data
        assert len(data["chunks"]) >= 1
        chunk = data["chunks"][0]
        assert "blob_id" in chunk
        assert "checksum" in chunk
        assert "size" in chunk

    def test_upload_session_status(self, session_id):
        resp = requests.get(f"{DATA}/v1/upload-session/{session_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == session_id
        assert isinstance(data["uploaded_chunks"], list)
        assert data["total_uploaded"] >= 1

    def test_idempotent_chunk_upload(self, session_id):
        """Re-uploading the same chunk_id must not create a duplicate."""
        with open(TEST_VIDEO, "rb") as f:
            data = f.read(1024 * 1024)
        resp = requests.post(
            f"{DATA}/v1/upload-chunk/{session_id}/chunk_0/0",
            files={"file": ("chunk_0", data, "application/octet-stream")},
        )
        assert resp.status_code == 200

        # Manifest should still have exactly one entry for this chunk
        manifest = requests.get(f"{DATA}/v1/manifest/{session_id}").json()
        chunk_ids = [c["chunk_id"] for c in manifest["chunks"]]
        assert chunk_ids.count("chunk_0") == 1


class TestVideoMetadata:
    def test_list_videos_public(self):
        resp = requests.get(f"{CONTROL}/v1/videos")
        assert resp.status_code == 200
        assert "videos" in resp.json()

    def test_list_videos_by_owner(self):
        resp = requests.get(f"{CONTROL}/v1/videos?owner=0xTestSuite")
        assert resp.status_code == 200
        assert isinstance(resp.json()["videos"], list)

    def test_search_videos(self):
        resp = requests.get(f"{CONTROL}/v1/videos?search=test")
        assert resp.status_code == 200

    def test_get_nonexistent_video(self):
        resp = requests.get(f"{CONTROL}/v1/videos/nonexistent-id")
        assert resp.status_code == 404

    def test_update_video_without_key_fails(self):
        resp = requests.patch(f"{CONTROL}/v1/videos/any-id", json={"title": "new"})
        assert resp.status_code in (401, 403)

    def test_delete_video_without_key_fails(self):
        resp = requests.delete(f"{CONTROL}/v1/videos/any-id")
        assert resp.status_code in (401, 403)


class TestAPIKeys:
    def test_generate_api_key(self):
        resp = requests.post(f"{CONTROL}/v1/api-keys", json={"owner": "0xKeyTest", "name": "test"})
        assert resp.status_code == 200
        data = resp.json()
        assert "api_key" in data
        assert data["api_key"].startswith("cv_")

    def test_list_api_keys(self):
        resp = requests.get(f"{CONTROL}/v1/api-keys/0xKeyTest")
        assert resp.status_code == 200
        assert "api_keys" in resp.json()

    def test_revoke_api_key(self):
        # Create, then revoke
        create = requests.post(f"{CONTROL}/v1/api-keys", json={"owner": "0xRevokeTest", "name": "revoke-me"})
        key = create.json()["api_key"]

        revoke = requests.delete(f"{CONTROL}/v1/api-keys/{key}", headers={"X-API-Key": key})
        assert revoke.status_code == 200

        # Revoked key should now fail auth
        after = requests.post(f"{CONTROL}/v1/upload-session", headers={"X-API-Key": key})
        assert after.status_code in (401, 403)


class TestWebhooks:
    def test_register_webhook(self, api_key):
        resp = requests.post(
            f"{CONTROL}/v1/webhooks",
            json={"url": "https://example.com/webhook", "events": ["upload.completed"]},
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data

    def test_list_webhooks(self, api_key):
        resp = requests.get(f"{CONTROL}/v1/webhooks", headers={"X-API-Key": api_key})
        assert resp.status_code == 200
        assert "webhooks" in resp.json()

    def test_webhook_signature_verification(self):
        import hashlib, hmac
        secret = "test_secret"
        payload = '{"event":"upload.completed"}'
        sig = "sha256=" + hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()

        # Correct signature
        resp = requests.post(
            f"{CONTROL}/v1/webhooks/verify",
            json={"payload": payload, "signature": sig},
        )
        assert resp.status_code == 200
        assert resp.json()["valid"] is False  # server uses its own SIGNING_SECRET, not "test_secret"

    def test_delete_webhook(self, api_key):
        # Create then delete
        create = requests.post(
            f"{CONTROL}/v1/webhooks",
            json={"url": "https://example.com/delete-me", "events": ["*"]},
            headers={"X-API-Key": api_key},
        )
        wh_id = create.json()["id"]
        delete = requests.delete(f"{CONTROL}/v1/webhooks/{wh_id}", headers={"X-API-Key": api_key})
        assert delete.status_code == 200


class TestMetrics:
    def test_metrics_endpoint(self):
        resp = requests.get(f"{CONTROL}/v1/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert "metrics" in data
        m = data["metrics"]
        assert "total_videos" in m
        assert "total_storage_bytes" in m
        assert "bandwidth" in m


class TestRateLimit:
    def test_rate_limit_triggers(self, api_key):
        """Burst 350 requests with the same API key — should eventually get 429."""
        hit_limit = False
        for _ in range(350):
            resp = requests.get(f"{CONTROL}/v1/videos", headers={"X-API-Key": api_key})
            if resp.status_code == 429:
                hit_limit = True
                break
        assert hit_limit, "Rate limiter did not trigger after 350 rapid requests"
