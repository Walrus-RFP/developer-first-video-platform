# API Specification
Developer-First Video Infrastructure Platform

This document defines the public APIs provided by the platform.

These APIs are designed for developers to upload, manage, and serve video assets.

The system separates control-plane APIs from data-plane APIs.

---

# 1. Control Plane APIs

Control plane handles metadata, upload sessions, and access policies.

Base URL example:
http://api.example.com

---

## 1.1 Create Upload Session

POST /upload-session

Creates a new upload session for a video.

Request:
None

Response:
{
  "upload_session_id": "uuid"
}

Description:
Client must create an upload session before uploading chunks.

---

## 1.2 Get Upload Session

GET /upload-session/{session_id}

Returns upload session status.

Response:
{
  "upload_session_id": "uuid",
  "status": "created | uploading | completed"
}

---

## 1.3 Complete Upload

POST /complete-upload/{session_id}

Marks upload as complete.

Response:
{
  "status": "upload completed"
}

Future behavior:
- Trigger manifest validation
- Register video asset metadata

---

## 1.4 Get Playback URL (Future)

GET /playback-url/{video_id}

Returns playback URL for video.

Response:
{
  "playback_url": "https://cdn.example.com/video/..."
}

---

## 1.5 Manage Video Metadata (Future)

POST /videos
GET /videos/{video_id}
PATCH /videos/{video_id}

Used for:
- Title
- Description
- Versioning
- Access policies

---

# 2. Data Plane APIs

Data plane handles actual video bytes.

Base URL example:
http://data.example.com

---

## 2.1 Upload Chunk

POST /upload-chunk/{session_id}/{chunk_id}

Uploads a video chunk.

Request:
multipart/form-data
file: binary chunk data

Response:
{
  "status": "chunk stored"
}

Behavior:
- Stores chunk in storage
- Associates chunk with upload session

---

## 2.2 Get Chunk (Future)

GET /chunk/{video_id}/{chunk_id}

Returns specific chunk.

Used for:
- Streaming
- Byte-range playback

---

## 2.3 Stream Video (Future)

GET /stream/{video_id}

Streams video using byte-range reads.

---

# 3. Event Hooks (Future)

Webhooks notify application when events happen.

Examples:

POST /webhook/upload-complete
POST /webhook/video-ready

Used for:
- Encoding pipeline
- Notifications
- Analytics

---

# 4. Error Handling

Standard error format:

{
  "error": "message",
  "code": "ERROR_CODE"
}

Examples:
SESSION_NOT_FOUND
UPLOAD_FAILED
ACCESS_DENIED

---

# 5. Authentication (Future)

Planned methods:

- API Keys
- OAuth tokens
- Signed upload URLs

---

# 6. Versioning

API versioning will use URL prefix:

/v1/upload-session
/v1/upload-chunk

This allows backward compatibility.

---

# 7. Design Principles

- Developer-first
- Simple upload workflow
- Clear separation of control and data planes
- Reusable video assets
- Scalable for large video files
