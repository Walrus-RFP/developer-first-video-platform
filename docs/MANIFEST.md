# Manifest Specification
Developer-First Video Infrastructure Platform

This document defines the structure and purpose of the manifest file used to reconstruct video assets from stored chunks.

The manifest is the source of truth for video structure, ordering, integrity, and metadata.

---

# 1. Purpose of Manifest

The manifest allows the system to:

- Reconstruct videos from chunks
- Validate integrity of uploaded data
- Enable partial reads and streaming
- Track metadata and versions
- Support reuse across applications

Without the manifest, chunks are just files.  
The manifest gives them meaning.

---

# 2. Manifest Location

Each upload session stores one manifest file.

Example:

storage/{session_id}/manifest.json

Future (Walrus):
walrus_bucket/{video_id}/manifest.json

---


---

## 3. Manifest Structure

Example `manifest.json`:

```json
{
  "video_id": "vid_123",
  "session_id": "abc123",
  "version": 1,

  "owner_id": "user_456",

  "created_at": "2026-02-18T10:00:00Z",

  "video_metadata": {
    "filename": "lecture.mp4",
    "duration_seconds": 3600,
    "resolution": "1920x1080",
    "codec": "h264",
    "size_bytes": 987654321
  },

  "chunk_info": {
    "chunk_size_bytes": 4194304,
    "total_chunks": 25,
    "ordered_chunks": [
      "chunk_0001",
      "chunk_0002",
      "chunk_0003"
    ]
  },

  "checksums": {
    "chunk_0001": "sha256:abc...",
    "chunk_0002": "sha256:def..."
  },

  "final_checksum": "sha256:xyz..."
}

---

# 4. Required Fields

| Field | Purpose |
|--------|---------|
video_id | Unique video asset identifier
session_id | Upload session reference
version | Version number
owner_id | Ownership and access control
created_at | Audit and debugging
chunk_info | Reconstruction details
checksums | Integrity validation

---

# 5. Manifest Lifecycle

1. Upload session created → empty manifest started
2. Chunks uploaded → manifest updated
3. Upload completed → final checksum added
4. Video marked READY

Reason:
Ensures correctness before playback.

---

# 6. Integrity Validation

When serving video:

1. Verify chunk exists
2. Validate checksum
3. Reassemble stream

Reason:
Detect corruption and maintain trust.

---

# 7. Versioning

Each new edit or replacement creates new version.

Example:

video_123_v1
video_123_v2

Old versions remain accessible.

Reason:
Supports education, archives, and reuse use cases.

---

# 8. Partial Playback

Player may request chunk range.

Manifest provides chunk order.

System streams only required chunks.

Reason:
Fast seeking and efficient playback.

---

# 9. Reuse Support

Multiple apps can reference the same manifest.

Example:

App A → video_123  
App B → video_123  

Reason:
Video becomes reusable platform asset.

---

# 10. Future Extensions

Manifest may include:

- subtitles
- thumbnails
- preview clips
- DRM info
- encryption keys
- analytics metadata

Reason:
Platform extensibility.

---

# 11. Why Manifest Is Important

It guarantees:

- Correct playback
- Data integrity
- Long-term durability
- Reusable video assets
- Scalable streaming

This is the foundation of the platform’s data model.
