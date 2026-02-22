import sqlite3
from datetime import datetime

DB_PATH = "video_metadata.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS videos (
        video_id TEXT PRIMARY KEY,
        owner TEXT,
        file_path TEXT,
        version INTEGER,
        status TEXT,
        created_at TEXT,
        checksum TEXT
    )
    """)

    conn.commit()
    conn.close()


# ⭐ FIXED: accept video_id from upload.py
def create_video(video_id: str, owner: str, file_path: str, checksum: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO videos (
        video_id, owner, file_path, version, status, created_at, checksum
    )
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        video_id,
        owner,
        file_path,
        1,
        "uploaded",
        datetime.utcnow().isoformat(),
        checksum
    ))

    conn.commit()
    conn.close()

    return video_id


def get_video_by_checksum(checksum: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT video_id, owner, file_path, version, status, created_at
        FROM videos
        WHERE checksum = ?
    """, (checksum,))

    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return {
        "video_id": row[0],
        "owner": row[1],
        "file_path": row[2],
        "version": row[3],
        "status": row[4],
        "created_at": row[5]
    }


from typing import Optional

def list_videos(owner: Optional[str] = None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    if owner:
        cursor.execute("""
            SELECT video_id, owner, file_path, version, status, created_at
            FROM videos
            WHERE owner = ?
            ORDER BY created_at DESC
        """, (owner,))
    else:
        cursor.execute("""
            SELECT video_id, owner, file_path, version, status, created_at
            FROM videos
            ORDER BY created_at DESC
        """)

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "video_id": r[0],
            "owner": r[1],
            "file_path": r[2],
            "version": r[3],
            "status": r[4],
            "created_at": r[5],
        }
        for r in rows
    ]


def get_video(video_id: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT video_id, owner, file_path, version, status, created_at
        FROM videos
        WHERE video_id = ?
    """, (video_id,))

    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return {
        "video_id": row[0],
        "owner": row[1],
        "file_path": row[2],
        "version": row[3],
        "status": row[4],
        "created_at": row[5]
    }


def get_db_stats():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM videos")
    count = cursor.fetchone()[0]

    # Simple estimate based on local HLS files (if any) or just count
    cursor.execute("SELECT owner, COUNT(*) FROM videos GROUP BY owner")
    owners = dict(cursor.fetchall())

    conn.close()

    return {
        "total_videos": count,
        "owner_distribution": owners,
        "storage_backend": "Walrus",
        "access_control": "Sui Move Registry"
    }