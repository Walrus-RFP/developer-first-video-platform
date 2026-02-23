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

app = FastAPI()

from control_plane.rate_limit import RateLimitMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RateLimitMiddleware)

# init DB
init_db()
init_webhooks_table()

# include upload routes under /v1 prefix
app.include_router(upload_router, prefix="/v1")

@app.get("/")
def root():
    return {"message": "Control plane running", "api_version": "v1"}


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
# AUTHENTICATION DEPENDENCY
# ---------------------------------------------------
from control_plane.auth import get_current_user, api_key_header
from control_plane.db import create_api_key, list_api_keys
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


# serve demo player
app.mount("/demo", StaticFiles(directory="demo", html=True), name="demo")

# serve HLS
os.makedirs("storage/hls", exist_ok=True)
app.mount("/hls", StaticFiles(directory="storage/hls"), name="hls")

@app.get("/thumbnail/{video_id}")
def get_thumbnail(video_id: str):
    path = os.path.join("storage", "hls", video_id, "thumbnail.jpg")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Thumbnail not found")
    return FileResponse(path)