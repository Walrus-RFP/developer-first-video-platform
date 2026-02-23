import os
from datetime import datetime
from typing import Optional
from sqlalchemy import create_engine, text, inspect

# Use SQLALCHEMY_DATABASE_URL or fallback to SQLite
DB_URL = os.getenv("DATABASE_URL", "sqlite:///video_metadata.db")

# Initialize the SQLAlchemy Engine
engine = create_engine(DB_URL, pool_pre_ping=True)


def init_db():
    with engine.begin() as conn:
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS videos (
            video_id VARCHAR PRIMARY KEY,
            owner VARCHAR,
            file_path VARCHAR,
            version INTEGER,
            status VARCHAR,
            created_at VARCHAR,
            checksum VARCHAR,
            title VARCHAR,
            description VARCHAR,
            duration_seconds REAL,
            resolution VARCHAR,
            file_size INTEGER,
            is_public INTEGER DEFAULT 1,
            encryption_key VARCHAR
        )
        """))

        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS api_keys (
            key VARCHAR PRIMARY KEY,
            owner VARCHAR,
            name VARCHAR,
            created_at VARCHAR
        )
        """))

        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS usage_logs (
            id INTEGER PRIMARY KEY,
            video_id VARCHAR,
            owner VARCHAR,
            type VARCHAR,
            bytes BIGINT,
            timestamp VARCHAR
        )
        """))

    # SQLAlchemy abstracts away schema migration typically, but we can safely ignore SQLite PRAGMAs.
    # We assume schema is up to date or managed via a real migration tool in prod.


def create_video(
    video_id: str,
    owner: str,
    file_path: str,
    checksum: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
    duration_seconds: Optional[float] = None,
    resolution: Optional[str] = None,
    file_size: Optional[int] = None,
    is_public: bool = True,
    encryption_key: Optional[str] = None,
):
    with engine.begin() as conn:
        conn.execute(text("""
        INSERT INTO videos (
            video_id, owner, file_path, version, status, created_at, checksum,
            title, description, duration_seconds, resolution, file_size, is_public, encryption_key
        )
        VALUES (
            :video_id, :owner, :file_path, :version, :status, :created_at, :checksum,
            :title, :description, :duration_seconds, :resolution, :file_size, :is_public, :encryption_key
        )
        """), {
            "video_id": video_id,
            "owner": owner,
            "file_path": file_path,
            "version": 1,
            "status": "uploaded",
            "created_at": datetime.utcnow().isoformat(),
            "checksum": checksum,
            "title": title,
            "description": description,
            "duration_seconds": duration_seconds,
            "resolution": resolution,
            "file_size": file_size,
            "is_public": 1 if is_public else 0,
            "encryption_key": encryption_key,
        })

    return video_id


def get_video_by_checksum(checksum: str):
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT video_id, owner, file_path, version, status, created_at,
                   title, description, duration_seconds, resolution, file_size
            FROM videos
            WHERE checksum = :checksum
        """), {"checksum": checksum}).mappings().fetchone()

    if not result:
        return None
    return dict(result)


_SELECT_COLS = """video_id, owner, file_path, version, status, created_at,
               title, description, duration_seconds, resolution, file_size, is_public, encryption_key"""


def list_videos(owner: Optional[str] = None):
    with engine.connect() as conn:
        if owner:
            result = conn.execute(text(f"""
                SELECT {_SELECT_COLS}
                FROM videos
                WHERE owner = :owner
                ORDER BY created_at DESC
            """), {"owner": owner}).mappings().fetchall()
        else:
            # Global feed: only show public videos
            result = conn.execute(text(f"""
                SELECT {_SELECT_COLS}
                FROM videos
                WHERE is_public = 1
                ORDER BY created_at DESC
            """)).mappings().fetchall()

    return [dict(r) for r in result]


def get_video(video_id: str):
    with engine.connect() as conn:
        result = conn.execute(text(f"""
            SELECT {_SELECT_COLS}
            FROM videos
            WHERE video_id = :video_id
        """), {"video_id": video_id}).mappings().fetchone()

    if not result:
        return None
    return dict(result)


def update_video(video_id: str, **fields):
    """Update metadata fields on an existing video."""
    allowed = {"title", "description", "status", "is_public"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return False

    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
    updates["video_id"] = video_id
    
    with engine.begin() as conn:
        res = conn.execute(text(f"UPDATE videos SET {set_clause} WHERE video_id = :video_id"), updates)
        return res.rowcount > 0


def delete_video(video_id: str):
    """Delete a video record from the database."""
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM videos WHERE video_id = :video_id"), {"video_id": video_id})
    return True


def log_usage(video_id: str, owner: str, type: str, bytes: int):
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO usage_logs (video_id, owner, type, bytes, timestamp)
            VALUES (:video_id, :owner, :type, :bytes, :timestamp)
        """), {
            "video_id": video_id,
            "owner": owner,
            "type": type,
            "bytes": bytes,
            "timestamp": datetime.utcnow().isoformat()
        })


def get_db_stats():
    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM videos")).scalar() or 0
        
        owners_rows = conn.execute(text("SELECT owner, COUNT(*) FROM videos GROUP BY owner")).fetchall()
        owners = {row[0]: row[1] for row in owners_rows}
        
        res = conn.execute(text("SELECT SUM(file_size), SUM(duration_seconds) FROM videos")).fetchone()
        total_size = res[0] or 0
        total_duration = res[1] or 0.0

        inspector = inspect(engine)
        has_webhooks = "webhooks" in inspector.get_table_names()
        
        webhook_stats = {"total": 0, "active": 0}
        if has_webhooks:
            wh_res = conn.execute(text("SELECT COUNT(*), SUM(CAST(active AS INTEGER)) FROM webhooks")).fetchone()
            webhook_stats["total"] = wh_res[0] or 0
            webhook_stats["active"] = wh_res[1] or 0

        ingress = conn.execute(text("SELECT SUM(bytes) FROM usage_logs WHERE type = 'ingress'")).scalar() or 0
        egress = conn.execute(text("SELECT SUM(bytes) FROM usage_logs WHERE type = 'egress'")).scalar() or 0
        recent = [dict(r) for r in conn.execute(text("SELECT type, bytes, timestamp FROM usage_logs ORDER BY timestamp DESC LIMIT 10")).mappings().fetchall()]

        return {
            "metrics": {
                "total_videos": count,
                "total_storage_bytes": total_size,
                "total_duration_seconds": total_duration,
                "webhooks": webhook_stats,
                "bandwidth": {
                    "ingress_total": ingress,
                    "egress_total": egress,
                }
            },
            "owner_distribution": owners,
            "recent_usage": recent,
            "platform_info": {
                "storage_backend": "Walrus",
                "access_control": "Sui Move Registry",
                "api_version": "v1"
            }
        }


# ---------------------------------------------------
# API KEYS
# ---------------------------------------------------
def create_api_key(api_key: str, owner: str, name: str):
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO api_keys (key, owner, name, created_at)
            VALUES (:key, :owner, :name, :created_at)
        """), {
            "key": api_key, "owner": owner, "name": name, 
            "created_at": datetime.utcnow().isoformat()
        })

def list_api_keys(owner: str):
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT key, name, created_at FROM api_keys WHERE owner = :owner
        """), {"owner": owner}).mappings().fetchall()
    return [dict(r) for r in result]

def get_api_key_owner(api_key: str) -> Optional[str]:
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT owner FROM api_keys WHERE key = :key
        """), {"key": api_key}).scalar()
    return result