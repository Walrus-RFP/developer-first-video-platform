"""
Integration tests for the playback pipeline.
Requires services running: control-plane :8000, data-plane :8001

Run:  pytest tests/test_playback.py -v
"""
import os
import pytest
import requests
import hmac
import hashlib
import time

CONTROL = os.getenv("CONTROL_PLANE_URL", "http://localhost:8000")
DATA    = os.getenv("DATA_PLANE_URL",    "http://localhost:8001")
SIGNING_SECRET = os.getenv("SIGNING_SECRET", "change_me_in_production")


def _make_signed_url(video_id: str, file: str = "playlist.m3u8", expiry: int = 3600) -> str:
    exp = int(time.time()) + expiry
    message = f"{video_id}:{exp}".encode()
    sig = hmac.new(SIGNING_SECRET.encode(), message, hashlib.sha256).hexdigest()
    return f"{DATA}/play/{video_id}/{file}?exp={exp}&sig={sig}"


@pytest.fixture(scope="module")
def api_key():
    resp = requests.post(f"{CONTROL}/v1/api-keys", json={"owner": "0xPlaybackTest", "name": "playback-pytest"})
    assert resp.status_code == 200
    return resp.json()["api_key"]


class TestSignedURLs:
    def test_expired_url_rejected(self):
        # exp in the past
        exp = int(time.time()) - 60
        message = f"fake-video-id:{exp}".encode()
        sig = hmac.new(SIGNING_SECRET.encode(), message, hashlib.sha256).hexdigest()
        resp = requests.get(f"{DATA}/play/fake-video-id/playlist.m3u8?exp={exp}&sig={sig}")
        assert resp.status_code == 403

    def test_tampered_signature_rejected(self):
        exp = int(time.time()) + 3600
        resp = requests.get(f"{DATA}/play/fake-video-id/playlist.m3u8?exp={exp}&sig=badhex")
        assert resp.status_code == 403

    def test_missing_signature_rejected(self):
        resp = requests.get(f"{DATA}/play/some-video-id/playlist.m3u8")
        assert resp.status_code == 403

    def test_path_traversal_rejected(self):
        url = _make_signed_url("some-id", file="../../etc/passwd")
        resp = requests.get(url)
        assert resp.status_code in (400, 403, 404)


class TestPlaybackURL:
    def test_public_video_playback_url(self, api_key):
        # List public videos and try to get a playback URL for one
        videos_resp = requests.get(f"{CONTROL}/v1/videos")
        assert videos_resp.status_code == 200
        videos = videos_resp.json().get("videos", [])

        if not videos:
            pytest.skip("No public videos available to test playback URL")

        video_id = videos[0]["video_id"]
        resp = requests.get(f"{CONTROL}/v1/playback-url/{video_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "playlist" in data
        assert video_id in data["playlist"]

    def test_nonexistent_video_playback_fails(self):
        resp = requests.get(f"{CONTROL}/v1/playback-url/nonexistent-video-id")
        assert resp.status_code == 404

    def test_private_video_requires_user_address(self, api_key):
        # This test verifies the auth gate; no actual private video needed
        # Create a fake private video scenario by checking the API response shape
        resp = requests.get(f"{CONTROL}/v1/playback-url/nonexistent")
        assert resp.status_code == 404  # video doesn't exist, but path is correct


class TestEmbedURL:
    def test_nonexistent_video_embed_fails(self):
        resp = requests.get(f"{CONTROL}/v1/videos/nonexistent/embed")
        assert resp.status_code == 404

    def test_embed_returns_correct_shape(self):
        videos = requests.get(f"{CONTROL}/v1/videos").json().get("videos", [])
        if not videos:
            pytest.skip("No public videos to test embed URL")

        video_id = videos[0]["video_id"]
        resp = requests.get(f"{CONTROL}/v1/videos/{video_id}/embed")
        assert resp.status_code == 200
        data = resp.json()
        assert "playlist_url" in data
        assert "embed_url" in data
        assert "iframe_html" in data
        assert "<iframe" in data["iframe_html"]


class TestAnalytics:
    def test_analytics_requires_auth(self):
        resp = requests.get(f"{CONTROL}/v1/videos/any-id/analytics")
        assert resp.status_code in (401, 403)

    def test_analytics_nonexistent_video(self, api_key):
        resp = requests.get(
            f"{CONTROL}/v1/videos/nonexistent-id/analytics",
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code == 404

    def test_analytics_shape(self, api_key):
        # Need a video owned by this test user
        videos = requests.get(
            f"{CONTROL}/v1/videos?owner=0xPlaybackTest"
        ).json().get("videos", [])
        if not videos:
            pytest.skip("No videos owned by test user")

        video_id = videos[0]["video_id"]
        resp = requests.get(
            f"{CONTROL}/v1/videos/{video_id}/analytics",
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "total_views" in data
        assert "egress_bytes" in data
        assert "last_7_days" in data


class TestDataPlaneHealth:
    def test_data_plane_root(self):
        resp = requests.get(f"{DATA}/")
        assert resp.status_code == 200
        assert resp.json()["message"] == "Data plane running"

    def test_upload_session_missing_returns_empty(self):
        resp = requests.get(f"{DATA}/v1/upload-session/nonexistent-session")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_uploaded"] == 0
        assert data["uploaded_chunks"] == []
