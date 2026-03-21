import os
import json
from datetime import datetime
from typing import Optional
from sqlalchemy import create_engine, text, inspect

DB_URL = os.getenv("DATABASE_URL", "sqlite:///video_metadata.db")
engine = create_engine(DB_URL, pool_pre_ping=True)
_IS_POSTGRES = DB_URL.startswith("postgresql") or DB_URL.startswith("postgres")


def init_db():
    with engine.begin() as conn:
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS videos (
            video_id VARCHAR PRIMARY KEY,
            owner VARCHAR,
            file_path VARCHAR,
            version INTEGER DEFAULT 1,
            status VARCHAR,
            created_at VARCHAR,
            updated_at VARCHAR,
            checksum VARCHAR,
            title VARCHAR,
            description VARCHAR,
            tags VARCHAR DEFAULT '[]',
            duration_seconds REAL,
            resolution VARCHAR,
            file_size INTEGER,
            is_public INTEGER DEFAULT 1,
            encryption_key VARCHAR,
            seal_key_blob_id VARCHAR,
            content_hash VARCHAR
        )
        """))

        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS api_keys (
            key VARCHAR PRIMARY KEY,
            owner VARCHAR,
            name VARCHAR,
            created_at VARCHAR,
            revoked INTEGER DEFAULT 0
        )
        """))

        id_col = "id SERIAL PRIMARY KEY" if _IS_POSTGRES else "id INTEGER PRIMARY KEY AUTOINCREMENT"
        conn.execute(text(f"""
        CREATE TABLE IF NOT EXISTS usage_logs (
            {id_col},
            video_id VARCHAR,
            owner VARCHAR,
            user_address VARCHAR,
            type VARCHAR,
            bytes BIGINT,
            timestamp VARCHAR
        )
        """))

        # Persistent upload status — replaces the in-memory UPLOAD_STATUS dict
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS upload_sessions (
            session_id VARCHAR PRIMARY KEY,
            status VARCHAR NOT NULL DEFAULT 'queued',
            video_id VARCHAR,
            error VARCHAR,
            playlist VARCHAR,
            sui_package_id VARCHAR,
            sui_registry_id VARCHAR,
            owner VARCHAR,
            created_at VARCHAR,
            updated_at VARCHAR
        )
        """))

    # Add columns that may be missing in existing DBs (safe no-op if already present)
    _add_column_if_missing("videos", "updated_at", "VARCHAR")
    _add_column_if_missing("videos", "tags", "VARCHAR DEFAULT '[]'")
    _add_column_if_missing("videos", "content_hash", "VARCHAR")
    _add_column_if_missing("api_keys", "revoked", "INTEGER DEFAULT 0")
    _add_column_if_missing("usage_logs", "user_address", "VARCHAR")
    _add_column_if_missing("upload_sessions", "sui_package_id", "VARCHAR")
    _add_column_if_missing("upload_sessions", "sui_registry_id", "VARCHAR")
    _add_column_if_missing("upload_sessions", "owner", "VARCHAR")
    _add_column_if_missing("upload_sessions", "content_hash", "VARCHAR")
    _add_column_if_missing("videos", "seal_key_blob_id", "VARCHAR")


def _add_column_if_missing(table: str, column: str, col_type: str):
    """Safely add a column to an existing table if it doesn't exist yet."""
    try:
        inspector = inspect(engine)
        existing = [c["name"] for c in inspector.get_columns(table)]
        if column not in existing:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
    except Exception:
        pass  # Table may not exist yet; init_db will create it


# ──────────────────────────────────────────────────────────────
# UPLOAD SESSION STATUS (replaces in-memory UPLOAD_STATUS dict)
# ──────────────────────────────────────────────────────────────

def set_upload_status(session_id: str, status: str, **kwargs):
    """Upsert upload session status into the DB."""
    now = datetime.utcnow().isoformat()
    # Build update fields
    fields = {
        "session_id": session_id,
        "status": status,
        "updated_at": now,
        "video_id": kwargs.get("video_id"),
        "error": kwargs.get("error"),
        "playlist": kwargs.get("playlist"),
        "sui_package_id": kwargs.get("sui_package_id"),
        "sui_registry_id": kwargs.get("sui_registry_id"),
        "owner": kwargs.get("owner"),
        "content_hash": kwargs.get("content_hash"),
    }
    with engine.begin() as conn:
        # Try update first, then insert
        res = conn.execute(text("""
            UPDATE upload_sessions
            SET status=:status, updated_at=:updated_at,
                video_id=COALESCE(:video_id, video_id),
                error=COALESCE(:error, error),
                playlist=COALESCE(:playlist, playlist),
                sui_package_id=COALESCE(:sui_package_id, sui_package_id),
                sui_registry_id=COALESCE(:sui_registry_id, sui_registry_id),
                content_hash=COALESCE(:content_hash, content_hash)
            WHERE session_id=:session_id
        """), fields)

        if res.rowcount == 0:
            fields["created_at"] = now
            conn.execute(text("""
                INSERT INTO upload_sessions
                    (session_id, status, video_id, error, playlist,
                     sui_package_id, sui_registry_id, owner, content_hash, created_at, updated_at)
                VALUES
                    (:session_id, :status, :video_id, :error, :playlist,
                     :sui_package_id, :sui_registry_id, :owner, :content_hash, :created_at, :updated_at)
            """), fields)


def get_upload_status(session_id: str) -> Optional[dict]:
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT session_id, status, video_id, error, playlist,
                   sui_package_id, sui_registry_id, owner, content_hash, created_at, updated_at
            FROM upload_sessions WHERE session_id=:sid
        """), {"sid": session_id}).mappings().fetchone()
    if not row:
        return None
    d = dict(row)
    # Return the same shape that UPLOAD_STATUS used to return
    result = {"status": d["status"]}
    if d.get("video_id"):
        result["video_id"] = d["video_id"]
    if d.get("error"):
        result["error"] = d["error"]
    if d.get("playlist"):
        result["playlist"] = d["playlist"]
    if d.get("sui_package_id"):
        result["sui_package_id"] = d["sui_package_id"]
    if d.get("sui_registry_id"):
        result["sui_registry_id"] = d["sui_registry_id"]
    if d.get("content_hash"):
        result["content_hash"] = d["content_hash"]
    return result


# ──────────────────────────────────────────────────────────────
# VIDEOS
# ──────────────────────────────────────────────────────────────

def create_video(
    video_id: str,
    owner: str,
    file_path: str,
    checksum: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
    tags: Optional[list] = None,
    duration_seconds: Optional[float] = None,
    resolution: Optional[str] = None,
    file_size: Optional[int] = None,
    is_public: bool = True,
    encryption_key: Optional[str] = None,
    seal_key_blob_id: Optional[str] = None,
    content_hash: Optional[str] = None,
):
    now = datetime.utcnow().isoformat()
    with engine.begin() as conn:
        conn.execute(text("""
        INSERT INTO videos (
            video_id, owner, file_path, version, status, created_at, updated_at, checksum,
            title, description, tags, duration_seconds, resolution, file_size, is_public,
            encryption_key, seal_key_blob_id, content_hash
        )
        VALUES (
            :video_id, :owner, :file_path, :version, :status, :created_at, :updated_at, :checksum,
            :title, :description, :tags, :duration_seconds, :resolution, :file_size, :is_public,
            :encryption_key, :seal_key_blob_id, :content_hash
        )
        """), {
            "video_id": video_id,
            "owner": owner,
            "file_path": file_path,
            "version": 1,
            "status": "uploaded",
            "created_at": now,
            "updated_at": now,
            "checksum": checksum,
            "title": title,
            "description": description,
            "tags": json.dumps(tags or []),
            "duration_seconds": duration_seconds,
            "resolution": resolution,
            "file_size": file_size,
            "is_public": 1 if is_public else 0,
            "encryption_key": encryption_key,
            "seal_key_blob_id": seal_key_blob_id,
            "content_hash": content_hash,
        })
    return video_id


def get_video_by_checksum(checksum: str):
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT video_id, owner, file_path, version, status, created_at,
                   title, description, duration_seconds, resolution, file_size,
                   is_public, encryption_key
            FROM videos WHERE checksum = :checksum
        """), {"checksum": checksum}).mappings().fetchone()
    return dict(result) if result else None


_SELECT_COLS = """video_id, owner, file_path, version, status, created_at, updated_at,
               title, description, tags, duration_seconds, resolution, file_size, is_public,
               encryption_key, seal_key_blob_id, content_hash"""


def list_videos(
    owner: Optional[str] = None,
    search: Optional[str] = None,
    tag: Optional[str] = None,
):
    conditions = []
    params: dict = {}

    if owner:
        conditions.append("owner = :owner")
        params["owner"] = owner
    else:
        conditions.append("is_public = 1")

    if search:
        conditions.append("(LOWER(title) LIKE :search OR LOWER(description) LIKE :search)")
        params["search"] = f"%{search.lower()}%"

    if tag:
        # tags stored as JSON array; use LIKE for simple substring match
        conditions.append("tags LIKE :tag")
        params["tag"] = f'%"{tag}"%'

    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    with engine.connect() as conn:
        result = conn.execute(
            text(f"SELECT {_SELECT_COLS} FROM videos {where} ORDER BY created_at DESC"),
            params,
        ).mappings().fetchall()
    return [_deserialize_video(dict(r)) for r in result]


def _deserialize_video(row: dict) -> dict:
    """Parse JSON-serialized fields back to Python types."""
    if "tags" in row and isinstance(row["tags"], str):
        try:
            row["tags"] = json.loads(row["tags"])
        except Exception:
            row["tags"] = []
    return row


def get_video(video_id: str):
    with engine.connect() as conn:
        result = conn.execute(text(f"""
            SELECT {_SELECT_COLS} FROM videos WHERE video_id = :video_id
        """), {"video_id": video_id}).mappings().fetchone()
    return _deserialize_video(dict(result)) if result else None


def update_video(video_id: str, **fields):
    allowed = {"title", "description", "tags", "status", "is_public"}
    updates = {}
    for k, v in fields.items():
        if k not in allowed or v is None:
            continue
        if k == "tags":
            updates[k] = json.dumps(v) if isinstance(v, list) else v
        else:
            updates[k] = v
    if not updates:
        return False
    updates["updated_at"] = datetime.utcnow().isoformat()
    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
    updates["video_id"] = video_id
    with engine.begin() as conn:
        res = conn.execute(text(f"UPDATE videos SET {set_clause} WHERE video_id = :video_id"), updates)
        return res.rowcount > 0


def store_seal_key(video_id: str, seal_key_blob_id: str):
    """Store the Walrus blob ID of the Seal-encrypted AES key and clear the plaintext key."""
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE videos
            SET seal_key_blob_id = :blob_id,
                encryption_key = NULL
            WHERE video_id = :vid
        """), {"blob_id": seal_key_blob_id, "vid": video_id})


def get_encryption_key(video_id: str) -> Optional[str]:
    """Return the plaintext AES key for a video (only present before Seal setup)."""
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT encryption_key FROM videos WHERE video_id = :vid"),
            {"vid": video_id}
        ).fetchone()
    return row[0] if row else None


def delete_video(video_id: str):
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM videos WHERE video_id = :video_id"), {"video_id": video_id})
    return True


# ──────────────────────────────────────────────────────────────
# USAGE LOGS
# ──────────────────────────────────────────────────────────────

def log_usage(video_id: str, owner: str, type: str, bytes: int, user_address: Optional[str] = None):
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO usage_logs (video_id, owner, user_address, type, bytes, timestamp)
                VALUES (:video_id, :owner, :user_address, :type, :bytes, :timestamp)
            """), {
                "video_id": video_id,
                "owner": owner,
                "user_address": user_address,
                "type": type,
                "bytes": bytes,
                "timestamp": datetime.utcnow().isoformat(),
            })
    except Exception as e:
        # Never crash the calling request over an analytics write failure
        from utils.logger import logger
        logger.warning("Failed to log usage: %s", e)


# ──────────────────────────────────────────────────────────────
# API KEYS
# ──────────────────────────────────────────────────────────────

def create_api_key(api_key: str, owner: str, name: str):
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO api_keys (key, owner, name, created_at, revoked)
            VALUES (:key, :owner, :name, :created_at, 0)
        """), {"key": api_key, "owner": owner, "name": name,
               "created_at": datetime.utcnow().isoformat()})


def list_api_keys(owner: str):
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT key, name, created_at FROM api_keys
            WHERE owner = :owner AND (revoked IS NULL OR revoked = 0)
        """), {"owner": owner}).mappings().fetchall()
    return [dict(r) for r in result]


def get_api_key_owner(api_key: str) -> Optional[str]:
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT owner FROM api_keys
            WHERE key = :key AND (revoked IS NULL OR revoked = 0)
        """), {"key": api_key}).scalar()
    return result


def revoke_api_key(api_key: str, owner: str) -> bool:
    with engine.begin() as conn:
        res = conn.execute(text("""
            UPDATE api_keys SET revoked = 1
            WHERE key = :key AND owner = :owner
        """), {"key": api_key, "owner": owner})
        return res.rowcount > 0


# ──────────────────────────────────────────────────────────────
# METRICS / STATS
# ──────────────────────────────────────────────────────────────

def get_video_analytics(video_id: str) -> dict:
    """Per-video analytics: view count, bandwidth, recent activity."""
    with engine.connect() as conn:
        # Total egress reads (proxy for view count)
        view_count = conn.execute(text("""
            SELECT COUNT(*) FROM usage_logs
            WHERE video_id = :vid AND type = 'egress'
        """), {"vid": video_id}).scalar() or 0

        bandwidth = conn.execute(text("""
            SELECT SUM(bytes) FROM usage_logs
            WHERE video_id = :vid AND type = 'egress'
        """), {"vid": video_id}).scalar() or 0

        ingress = conn.execute(text("""
            SELECT SUM(bytes) FROM usage_logs
            WHERE video_id = :vid AND type = 'ingress'
        """), {"vid": video_id}).scalar() or 0

        # Unique viewers (by user_address where available)
        unique_viewers = conn.execute(text("""
            SELECT COUNT(DISTINCT user_address) FROM usage_logs
            WHERE video_id = :vid AND type = 'egress' AND user_address IS NOT NULL
        """), {"vid": video_id}).scalar() or 0

        # Activity over the last 7 days grouped by day
        if _IS_POSTGRES:
            seven_days_ago = "TO_CHAR(NOW() - INTERVAL '7 days', 'YYYY-MM-DD')"
        else:
            seven_days_ago = "DATE('now', '-7 days')"
        daily = conn.execute(text(f"""
            SELECT SUBSTR(timestamp, 1, 10) as day, COUNT(*) as views, SUM(bytes) as bytes
            FROM usage_logs
            WHERE video_id = :vid AND type = 'egress'
              AND timestamp >= {seven_days_ago}
            GROUP BY day ORDER BY day
        """), {"vid": video_id}).fetchall()

    return {
        "video_id": video_id,
        "total_views": view_count,
        "unique_viewers": unique_viewers,
        "egress_bytes": bandwidth,
        "ingress_bytes": ingress,
        "last_7_days": [{"day": r[0], "views": r[1], "bytes": r[2]} for r in daily],
    }


def get_db_stats():
    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM videos")).scalar() or 0

        owners_rows = conn.execute(
            text("SELECT owner, COUNT(*) FROM videos GROUP BY owner")
        ).fetchall()
        owners = {row[0]: row[1] for row in owners_rows}

        res = conn.execute(
            text("SELECT SUM(file_size), SUM(duration_seconds) FROM videos")
        ).fetchone()
        total_size = res[0] or 0
        total_duration = res[1] or 0.0

        inspector = inspect(engine)
        has_webhooks = "webhooks" in inspector.get_table_names()

        webhook_stats = {"total": 0, "active": 0}
        if has_webhooks:
            wh_res = conn.execute(
                text("SELECT COUNT(*), SUM(CAST(active AS INTEGER)) FROM webhooks")
            ).fetchone()
            webhook_stats["total"] = wh_res[0] or 0
            webhook_stats["active"] = wh_res[1] or 0

        ingress = conn.execute(
            text("SELECT SUM(bytes) FROM usage_logs WHERE type = 'ingress'")
        ).scalar() or 0
        egress = conn.execute(
            text("SELECT SUM(bytes) FROM usage_logs WHERE type = 'egress'")
        ).scalar() or 0
        recent = [dict(r) for r in conn.execute(
            text("SELECT type, bytes, timestamp FROM usage_logs ORDER BY timestamp DESC LIMIT 10")
        ).mappings().fetchall()]

        upload_row = conn.execute(text("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status = 'upload completed' THEN 1 ELSE 0 END) as succeeded,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                SUM(CASE WHEN status NOT IN ('upload completed', 'failed') THEN 1 ELSE 0 END) as in_progress
            FROM upload_sessions
        """)).fetchone()
        upload_stats = {
            "total": upload_row[0] or 0,
            "succeeded": upload_row[1] or 0,
            "failed": upload_row[2] or 0,
            "in_progress": upload_row[3] or 0,
            "success_rate": round(
                (upload_row[1] or 0) / max(upload_row[0] or 1, 1) * 100, 1
            ),
        }

        return {
            "metrics": {
                "total_videos": count,
                "total_storage_bytes": total_size,
                "total_duration_seconds": total_duration,
                "webhooks": webhook_stats,
                "bandwidth": {"ingress_total": ingress, "egress_total": egress},
                "uploads": upload_stats,
            },
            "owner_distribution": owners,
            "recent_usage": recent,
            "platform_info": {
                "storage_backend": "Walrus",
                "access_control": "Sui Move Registry",
                "api_version": "v1",
            },
        }
