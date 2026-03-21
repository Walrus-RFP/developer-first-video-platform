from dotenv import load_dotenv
load_dotenv()  # Load .env before any module reads os.environ

from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from control_plane.upload import router as upload_router
from control_plane.db import init_db
from control_plane.webhooks import init_webhooks_table, register_webhook, list_webhooks, delete_webhook
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional
import os

from utils.logger import logger
logger.info("Control plane main loaded")

from control_plane.auth import get_current_user, api_key_header

app = FastAPI(
    title="Walrus Video Platform — Control Plane",
    description=(
        "Upload sessions, video metadata, API key management, webhooks, "
        "on-chain access grant queries, subscription policies, Seal policy linking, "
        "and signed playback URL generation. "
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

# init DB
init_db()
init_webhooks_table()

# include upload routes under /v1 prefix
app.include_router(upload_router, prefix="/v1")

@app.get("/")
def root():
    return {"message": "Control plane running", "api_version": "v1"}

@app.get("/v1/debug-logs")
def get_logs(owner: str = Depends(get_current_user)):
    try:
        with open("app.log", "r") as f:
            lines = f.readlines()
            return {"logs": "".join(lines[-100:])}
    except Exception as e:
        return {"error": str(e)}


@app.get("/v1/metrics")
def metrics():
    from control_plane.db import get_db_stats
    import shutil
    import os
    
    stats = get_db_stats()
    
    # Add system-level metrics
    disk = shutil.disk_usage("/")
    stats["system"] = {
        "disk_total_gb": round(disk.total / (1024**3), 2),
        "disk_used_gb": round(disk.used / (1024**3), 2),
        "disk_free_gb": round(disk.free / (1024**3), 2),
    }
    
    # Try to get load average (Unix only)
    try:
        load1, load5, load15 = os.getloadavg()
        stats["system"]["load_average"] = {
            "1m": round(load1, 2),
            "5m": round(load5, 2),
            "15m": round(load15, 2)
        }
    except AttributeError:
        pass
        
    return stats


# ---------------------------------------------------
# API KEY MANAGEMENT ENDPOINTS
# ---------------------------------------------------
from control_plane.db import create_api_key, list_api_keys, revoke_api_key
import secrets

# ---------------------------------------------------
# API KEY MANAGEMENT ENDPOINTS
# ---------------------------------------------------
class APIKeyCreate(BaseModel):
    owner: str
    name: str

@app.post("/v1/api-keys")
def generate_api_key(body: APIKeyCreate):
    """Generate a new API key for a user. Public in demo to enable dashboard setup."""
    new_key = f"cv_{secrets.token_urlsafe(32)}"
    create_api_key(new_key, body.owner, body.name)
    return {"api_key": new_key, "owner": body.owner, "name": body.name}

@app.get("/v1/api-keys/{owner}")
def get_user_keys(owner: str):
    return {"api_keys": list_api_keys(owner)}

@app.delete("/v1/api-keys/{api_key}")
def delete_api_key(api_key: str, owner: str = Depends(get_current_user)):
    revoked = revoke_api_key(api_key, owner)
    if not revoked:
        raise HTTPException(status_code=404, detail="API key not found or not owned by you")
    return {"status": "revoked"}


# ---------------------------------------------------
# WEBHOOK MANAGEMENT ENDPOINTS
# ---------------------------------------------------
class WebhookCreate(BaseModel):
    url: str
    events: List[str]  # e.g. ["upload.completed", "video.registered"] or ["*"]
    owner: Optional[str] = None

@app.post("/v1/webhooks")
def create_webhook(body: WebhookCreate, owner: str = Depends(get_current_user)):
    return register_webhook(url=body.url, events=body.events, owner=owner)

@app.get("/v1/webhooks")
def get_webhooks(owner: str = Depends(get_current_user)):
    return {"webhooks": list_webhooks(owner=owner)}

@app.delete("/v1/webhooks/{webhook_id}")
def remove_webhook(webhook_id: str, owner: str = Depends(get_current_user)):
    if not delete_webhook(webhook_id):
        raise HTTPException(status_code=404, detail="Webhook not found")
    return {"status": "deleted"}


class WebhookVerifyRequest(BaseModel):
    payload: str         # raw request body as string
    signature: str       # value of X-Webhook-Signature header (sha256=<hex>)

@app.post("/v1/webhooks/verify")
def verify_webhook_signature(body: WebhookVerifyRequest):
    """
    Helper endpoint for developers to verify webhook delivery signatures.
    Returns { valid: bool }.  In production, do this check server-side in your receiver.
    """
    import hashlib, hmac, os
    secret = os.environ.get("SIGNING_SECRET", "super_secret_key_change_me")
    expected = "sha256=" + hmac.new(secret.encode(), body.payload.encode(), hashlib.sha256).hexdigest()
    valid = hmac.compare_digest(expected, body.signature)
    return {"valid": valid}


# ---------------------------------------------------
# ACCESS CONTROL (on-chain grants, read from auth proxy)
# ---------------------------------------------------
import urllib.request as _ureq
import urllib.error as _uerr

_AUTH_PROXY = os.environ.get("SUI_AUTH_PROXY_URL", "http://localhost:8002")

@app.get("/v1/access/{video_id}/grants")
def list_access_grants(video_id: str, owner: str = Depends(get_current_user)):
    """
    Returns current on-chain access grants for a video (fetched from sui-auth-proxy).
    Only the video owner may call this endpoint.
    """
    from control_plane.db import get_video
    video = get_video(video_id)
    if not video:
        raise HTTPException(404, "Video not found")
    if video.get("owner") != owner:
        raise HTTPException(403, "Not authorized")

    try:
        url = f"{_AUTH_PROXY}/grants?video_id={video_id}"
        req = _ureq.Request(url, method="GET")
        req.add_header("User-Agent", "WalrusControlPlane/1.0")
        with _ureq.urlopen(req, timeout=5) as resp:
            import json as _json
            return _json.loads(resp.read())
    except _uerr.HTTPError as e:
        raise HTTPException(e.code, f"Auth proxy error: {e.reason}")
    except Exception:
        # Auth proxy unavailable or contracts not deployed — return empty list
        return {"grants": []}


# ---------------------------------------------------
# SUBSCRIPTION POLICY ENDPOINTS
# ---------------------------------------------------
class SubscriptionPolicyCreate(BaseModel):
    price_mist: int
    duration_epochs: int
    revenue_address: str

@app.get("/v1/subscription/{video_id}")
def get_subscription_policy(video_id: str):
    """
    Returns the on-chain subscription policy for a video (via sui-auth-proxy).
    Public — no auth required (used by purchase flows and storefronts).
    """
    try:
        url = f"{_AUTH_PROXY}/subscription-policy?video_id={video_id}"
        req = _ureq.Request(url, method="GET")
        req.add_header("User-Agent", "WalrusControlPlane/1.0")
        with _ureq.urlopen(req, timeout=5) as resp:
            import json as _json
            return _json.loads(resp.read())
    except _uerr.HTTPError as e:
        raise HTTPException(e.code, f"Auth proxy error: {e.reason}")
    except Exception:
        return {"has_policy": False, "price_mist": 0}

@app.post("/v1/subscription/{video_id}")
def create_subscription_policy(
    video_id: str,
    body: SubscriptionPolicyCreate,
    owner: str = Depends(get_current_user),
):
    """
    Returns Sui transaction parameters for the client to sign.
    The wallet executes access_control::set_subscription_policy on-chain.
    """
    from control_plane.db import get_video as _get_video
    video = _get_video(video_id)
    if not video:
        raise HTTPException(404, "Video not found")
    if video.get("owner") != owner:
        raise HTTPException(403, "Not authorized")
    from utils.sui import PACKAGE_ID, REGISTRY_ID, ACCESS_STORE_ID
    return {
        "video_id": video_id,
        "sui_package_id": PACKAGE_ID,
        "sui_registry_id": REGISTRY_ID,
        "sui_access_store_id": ACCESS_STORE_ID,
        "sui_call": "set_subscription_policy",
        "arguments": {
            "price_mist": body.price_mist,
            "duration_epochs": body.duration_epochs,
            "revenue_address": body.revenue_address,
        },
        "message": "Sign the Sui transaction to install this subscription policy on-chain.",
    }


# ---------------------------------------------------
# SEAL POLICY ENDPOINTS
# ---------------------------------------------------
class SealPolicyLink(BaseModel):
    seal_policy_id: str

@app.post("/v1/videos/{video_id}/seal-policy")
def link_seal_policy(
    video_id: str,
    body: SealPolicyLink,
    owner: str = Depends(get_current_user),
):
    """
    Returns Sui transaction parameters for the client to sign.
    The wallet executes video_registry::link_seal_policy on-chain.

    Client-side Seal flow:
      1. Deploy a Seal policy object on Sui (Mysten Seal SDK / CLI).
      2. Call this endpoint with the resulting seal_policy_id.
      3. Sign and execute the returned Sui transaction.
      4. Future playback will use Seal for key distribution.
         AES-GCM remains active as a working fallback for non-Seal clients.
    """
    from control_plane.db import get_video as _get_video
    video = _get_video(video_id)
    if not video:
        raise HTTPException(404, "Video not found")
    if video.get("owner") != owner:
        raise HTTPException(403, "Not authorized")
    from utils.sui import PACKAGE_ID, REGISTRY_ID
    return {
        "video_id": video_id,
        "seal_policy_id": body.seal_policy_id,
        "sui_package_id": PACKAGE_ID,
        "sui_registry_id": REGISTRY_ID,
        "sui_call": "link_seal_policy",
        "message": (
            "Sign the Sui transaction to link this Seal policy on-chain. "
            "AES-GCM encryption remains active as a fallback for legacy clients."
        ),
    }

@app.get("/v1/videos/{video_id}/seal-policy")
def get_seal_policy(video_id: str):
    """Returns the Seal policy ID linked to this video, if any."""
    try:
        url = f"{_AUTH_PROXY}/seal-policy?video_id={video_id}"
        req = _ureq.Request(url, method="GET")
        req.add_header("User-Agent", "WalrusControlPlane/1.0")
        with _ureq.urlopen(req, timeout=5) as resp:
            import json as _json
            return _json.loads(resp.read())
    except Exception:
        return {"seal_policy_id": None, "linked": False}


# serve HLS
os.makedirs("storage/hls", exist_ok=True)
app.mount("/hls", StaticFiles(directory="storage/hls"), name="hls")

@app.get("/thumbnail/{video_id}")
def get_thumbnail(video_id: str):
    path = os.path.join("storage", "hls", video_id, "thumbnail.jpg")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Thumbnail not found")
    return FileResponse(path)