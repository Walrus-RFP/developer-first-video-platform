# Storage Format Specification
Developer-First Video Infrastructure Platform

This document defines how video data is stored in the system.

The storage format is designed for durability, reuse, and efficient streaming.

---

# 1. Storage Goals

The storage system must support:

- Large video uploads
- Resumable uploads
- Partial reads
- Efficient playback
- Reusable video assets
- Long-term durability

---

# 2. Storage Structure

Each video upload session is stored as a directory (or Walrus bucket in future).

Example:

storage/
    {session_id}/
        chunk_0001
        chunk_0002
        chunk_0003
        manifest.json

Future with Walrus:

walrus_bucket/{video_id}/chunks/{chunk_id}

---

# 3. Chunk Format

Video is split into fixed-size chunks.

Example chunk size:
4 MB – 16 MB (configurable)

Reason:
- Large chunks → faster upload
- Small chunks → better retry control

---

## 3.1 Chunk Naming

Chunks are named using ordered IDs.

Example:
chunk_0001
chunk_0002
chunk_0003

Reason:
Allows easy ordering during playback.

Alternative naming:
{video_id}_{chunk_index}

---

## 3.2 Chunk Metadata

Each chunk has metadata:

chunk_id  
session_id  
checksum  
size  
upload_timestamp  

Stored in:
- manifest file
- metadata database (future control plane)

Reason:
Supports integrity validation.

---

# 4. Manifest File

Each video upload has a manifest file.

Example:

manifest.json

Contains:

{
  "video_id": "...",
  "total_chunks": 10,
  "chunk_order": ["chunk_0001", "chunk_0002"],
  "checksums": {...},
  "video_duration": "...",
  "codec": "...",
  "resolution": "..."
}

Reason:
Allows video reconstruction without reprocessing.

---

# 5. Storage Backend

Current implementation:
Local filesystem (storage/ folder)

Future implementation:
Walrus blob storage.

Chunks stored as blobs.
Manifest stored as metadata object.

Reason:
Walrus provides durable and portable storage.

---

# 6. Partial Read Support

Chunks must support byte-range reads.

This allows:
- Fast seeking
- Progressive playback
- CDN caching

Example flow:

Player → request chunk 005 → storage returns only needed bytes.

---

# 7. Versioning Support

Each video asset may have versions.

Example:

video_123/
    v1/
    v2/

Reason:
Allows updates without losing old content.

---

# 8. Reuse Support

Videos are stored independent of applications.

Multiple apps can reference same video asset.

Reason:
Platform treats video as first-class data asset.

---

# 9. Integrity Checks

Each chunk stores checksum.

Manifest stores global checksum.

Reason:
Detect corruption and ensure long-term reliability.

---

# 10. Why This Format Works

- Supports large-file uploads
- Supports resumable uploads
- Supports streaming
- Supports durability
- Supports reuse
- Matches project requirements
