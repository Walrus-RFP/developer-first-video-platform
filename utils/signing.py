import hashlib
import hmac
import time
import urllib.parse
import os

SECRET = "super_secret_key_change_me"
DATA_PLANE_URL = os.environ.get("DATA_PLANE_URL", "http://127.0.0.1:8001")


# =====================================================
# CREATE SIGNED URL
# =====================================================
def create_signed_url(video_id: str, file: str = "playlist.m3u8", expiry_seconds=3600):

    exp = int(time.time()) + expiry_seconds
    message = f"{video_id}:{exp}".encode()

    sig = hmac.new(SECRET.encode(), message, hashlib.sha256).hexdigest()

    return (
        f"{DATA_PLANE_URL}/play/{video_id}/{file}"
        f"?exp={exp}&sig={sig}"
    )


# =====================================================
# VERIFY SIGNED URL
# =====================================================
def verify_signed_url(video_id: str, params, file: str = "playlist.m3u8"):

    exp = params.get("exp")
    sig = params.get("sig")

    if not exp or not sig:
        return False

    if int(exp) < int(time.time()):
        return False

    message = f"{video_id}:{exp}".encode()
    expected = hmac.new(SECRET.encode(), message, hashlib.sha256).hexdigest()

    return hmac.compare_digest(expected, sig)