"""
Webhook event system for the video platform.

Supported events:
  - upload.completed   — fired when a video upload finishes processing
  - video.registered   — fired when a video is registered on-chain
  - playback.requested — fired when a signed playback URL is generated

Webhook deliveries include an X-Webhook-Signature header (HMAC-SHA256)
so receivers can verify the payload came from this platform.
"""

import hashlib
import hmac
import json
import os
import uuid
import urllib.request
import urllib.error
from datetime import datetime
from threading import Thread
from typing import Optional, List
from sqlalchemy import text

from control_plane.db import engine
from utils.logger import logger

WEBHOOK_SECRET = os.environ.get("SIGNING_SECRET", "super_secret_key_change_me")


# ──────────────────────────────────────────────────────────────
# DB SCHEMA
# ──────────────────────────────────────────────────────────────

def init_webhooks_table():
    with engine.begin() as conn:
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS webhooks (
            id VARCHAR PRIMARY KEY,
            url VARCHAR NOT NULL,
            events VARCHAR NOT NULL,
            owner VARCHAR,
            active INTEGER DEFAULT 1,
            created_at VARCHAR
        )
        """))
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS webhook_logs (
            id VARCHAR PRIMARY KEY,
            webhook_id VARCHAR,
            event VARCHAR,
            payload VARCHAR,
            status_code INTEGER,
            error VARCHAR,
            created_at VARCHAR
        )
        """))


# ──────────────────────────────────────────────────────────────
# CRUD
# ──────────────────────────────────────────────────────────────

def register_webhook(url: str, events: List[str], owner: Optional[str] = None) -> dict:
    wh_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO webhooks (id, url, events, owner, active, created_at)
            VALUES (:id, :url, :events, :owner, 1, :created_at)
        """), {
            "id": wh_id,
            "url": url,
            "events": json.dumps(events),
            "owner": owner,
            "created_at": datetime.utcnow().isoformat(),
        })
    return {"id": wh_id, "url": url, "events": events, "active": True}


def list_webhooks(owner: Optional[str] = None) -> list:
    with engine.connect() as conn:
        if owner:
            rows = conn.execute(text("""
                SELECT id, url, events, owner, active, created_at
                FROM webhooks WHERE owner = :owner
            """), {"owner": owner}).mappings().fetchall()
        else:
            rows = conn.execute(text("""
                SELECT id, url, events, owner, active, created_at FROM webhooks
            """)).mappings().fetchall()

    return [
        {
            "id": r["id"],
            "url": r["url"],
            "events": json.loads(r["events"]),
            "owner": r["owner"],
            "active": bool(r["active"]),
            "created_at": r["created_at"],
        }
        for r in rows
    ]


def delete_webhook(wh_id: str) -> bool:
    with engine.begin() as conn:
        res = conn.execute(text("DELETE FROM webhooks WHERE id = :id"), {"id": wh_id})
        return res.rowcount > 0


# ──────────────────────────────────────────────────────────────
# EVENT DISPATCH
# ──────────────────────────────────────────────────────────────

def _sign_payload(body: bytes) -> str:
    """Return an HMAC-SHA256 hex digest of the raw body."""
    return hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()


def _deliver(webhook: dict, event: str, payload: dict):
    """
    Send a webhook POST with exponential backoff retries.
    Schedule: immediate, 2s, 4s, 8s (4 attempts total).
    4xx responses are not retried — they indicate a permanent client error.
    """
    import time as _time

    body = json.dumps({
        "event": event,
        "data": payload,
        "timestamp": datetime.utcnow().isoformat(),
    }).encode()

    signature = _sign_payload(body)
    log_id = str(uuid.uuid4())
    status_code = None
    error = None

    MAX_ATTEMPTS = 4
    BACKOFF = [0, 2, 4, 8]

    for attempt in range(MAX_ATTEMPTS):
        if BACKOFF[attempt] > 0:
            _time.sleep(BACKOFF[attempt])
        try:
            req = urllib.request.Request(webhook["url"], data=body, method="POST")
            req.add_header("Content-Type", "application/json")
            req.add_header("User-Agent", "WalrusVideoWebhook/1.0")
            req.add_header("X-Webhook-Event", event)
            req.add_header("X-Webhook-Signature", f"sha256={signature}")
            req.add_header("X-Webhook-Attempt", str(attempt + 1))
            with urllib.request.urlopen(req, timeout=10) as resp:
                status_code = resp.status
            error = None
            break  # success
        except urllib.error.HTTPError as e:
            status_code = e.code
            error = str(e)
            if 400 <= e.code < 500:
                break  # 4xx won't self-heal — stop retrying
        except Exception as e:
            error = str(e)

    try:
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO webhook_logs
                    (id, webhook_id, event, payload, status_code, error, created_at)
                VALUES
                    (:id, :webhook_id, :event, :payload, :status_code, :error, :created_at)
            """), {
                "id": log_id,
                "webhook_id": webhook["id"],
                "event": event,
                "payload": json.dumps(payload),
                "status_code": status_code,
                "error": error,
                "created_at": datetime.utcnow().isoformat(),
            })
    except Exception as e:
        logger.error("Failed to log webhook delivery: %s", e)

    if error:
        logger.error(
            "Failed to deliver %s to %s: %s",
            event, webhook["url"], error,
            extra={"event": event, "url": webhook["url"]},
        )
    else:
        logger.info(
            "Delivered %s to %s (HTTP %d)",
            event, webhook["url"], status_code,
            extra={"event": event, "url": webhook["url"], "status_code": status_code},
        )


def fire_event(event: str, payload: dict):
    """
    Fire an event to all subscribed webhooks.
    Delivery is non-blocking (background daemon threads).
    """
    try:
        webhooks = list_webhooks()
        for wh in webhooks:
            if not wh["active"]:
                continue
            if event in wh["events"] or "*" in wh["events"]:
                Thread(target=_deliver, args=(wh, event, payload), daemon=True).start()
    except Exception as e:
        logger.error("Error dispatching webhook event: %s", e, extra={"event": event})
