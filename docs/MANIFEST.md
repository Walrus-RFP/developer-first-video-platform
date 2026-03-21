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

Each upload session stores one manifest file during the chunk upload phase:

```
storage/{session_id}/manifest.json
```

After the upload completes and HLS transcoding runs, the Control Plane stores HLS asset blob IDs (indexed by file path) in the same manifest under the `hls_assets` key. The completed manifest is then retrievable via the Control Plane at `/v1/hls-manifest/{video_id}`.

---


---

## 3. Manifest Structure

The manifest during chunk upload:

```json
{
  "session_id": "abc123",
  "chunks": [
    {
      "chunk_id": "chunk_0",
      "chunk_index": 0,
      "blob_id": "BNi4xW...",
      "checksum": "sha256:abc...",
      "size": 4194304
    },
    {
      "chunk_id": "chunk_1",
      "chunk_index": 1,
      "blob_id": "Cq7mRx...",
      "checksum": "sha256:def...",
      "size": 4194304
    }
  ]
}
```

After HLS processing completes, the manifest gains an `hls_assets` map (filename → Walrus blob ID):

```json
{
  "session_id": "abc123",
  "chunks": [ ... ],
  "hls_assets": {
    "index.m3u8":       "Dp9kTz...",
    "1080p/index.m3u8": "Eq2wVy...",
    "1080p/seg000.ts":  "Fr3xUz...",
    "720p/index.m3u8":  "Gs4yWa...",
    "thumbnail.jpg":    "Ht5zXb..."
  }
}
```

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
