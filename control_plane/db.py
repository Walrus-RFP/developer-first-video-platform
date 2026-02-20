import sqlite3
import uuid
from datetime import datetime

DB_PATH = "video_metadata.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Create table with checksum column
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


def create_video(owner: str, file_path: str, checksum: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    video_id = str(uuid.uuid4())

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


def list_videos():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT video_id, owner, file_path, version, status, created_at
        FROM videos
        ORDER BY created_at DESC
    """)

    rows = cursor.fetchall()
    conn.close()

    videos = []
    for r in rows:
        videos.append({
            "video_id": r[0],
            "owner": r[1],
            "file_path": r[2],
            "version": r[3],
            "status": r[4],
            "created_at": r[5]
        })

    return videos


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