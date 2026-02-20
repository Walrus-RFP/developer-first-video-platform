import time
import hmac
import hashlib
import urllib.parse

SECRET = "super-secret-key"


def create_signed_url(video_id, expiry_seconds=3600):
    expiry = int(time.time()) + expiry_seconds
    msg = f"{video_id}:{expiry}".encode()

    signature = hmac.new(
        SECRET.encode(),
        msg,
        hashlib.sha256
    ).hexdigest()

    query = urllib.parse.urlencode({
        "exp": expiry,
        "sig": signature
    })

    return f"http://127.0.0.1:8001/play/{video_id}?{query}"


def verify_signed_url(video_id, params):
    try:
        exp = int(params.get("exp"))
        sig = params.get("sig")

        if time.time() > exp:
            return False

        msg = f"{video_id}:{exp}".encode()

        expected = hmac.new(
            SECRET.encode(),
            msg,
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(sig, expected)

    except Exception:
        return False