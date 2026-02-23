# API Specification
Developer-First Video Infrastructure Platform

This document defines the public REST APIs provided by the platform. The system separates control-plane APIs (metadata, auth, orchestration) from data-plane APIs (heavy streaming and storage).

All endpoints are prefixed with `/v1`.

### Authentication
All modifying endpoints on the Control Plane require an `X-API-Key` header with a valid Developer API Key.

---

# 1. Control Plane APIs (Port 8000)

## 1.1 API Keys & Auth

### Generate API Key
`POST /v1/api-keys`
Requires valid owner authentication (currently bootstrapped to "self").
**Request Body:**
```json
{
  "owner": "string",
  "name": "string"
}
```

### List API Keys
`GET /v1/api-keys/{owner}`
Returns all API keys for the specified owner.

---

## 1.2 Video Upload Orchestration

### Create Upload Session
`POST /v1/upload-session`
Initializes a new multipart upload session.
**Headers:** `X-API-Key: <your_key>`
**Response:**
```json
{
  "upload_session_id": "uuid",
  "upload_path": "string"
}
```

### Complete Upload
`POST /v1/complete-upload/{session_id}`
Triggers chunk merging, HLS conversion, Walrus upload, and on-chain setup.
**Headers:** `X-API-Key: <your_key>`
**Query Params:**
- `title` (optional string)
- `is_public` (optional boolean, default true)
**Response:**
```json
{
  "status": "upload completed",
  "video_id": "uuid",
  "sui_package_id": "0x...",
  "sui_registry_id": "0x..."
}
```

---

## 1.3 Video Management & Playback

### Get Video Metadata
`GET /v1/videos/{video_id}`
Returns video metadata (title, duration, resolution, size, status).

### Update Video Metadata
`PATCH /v1/videos/{video_id}`
**Headers:** `X-API-Key: <your_key>`
**Request Body:**
```json
{
  "title": "string (optional)",
  "description": "string (optional)",
  "is_public": "boolean (optional)"
}
```

### Get Playback URL
`GET /v1/playback-url/{video_id}?user_address=0x...`
Returns a signed streaming URL. 
*Note: If `is_public` is false, `user_address` is strictly required and validated against the Sui blockchain (`sui_devInspectTransactionBlock`) before returning the URL.*

---

## 1.4 Webhooks (Events)

### Register Webhook
`POST /v1/webhooks`
**Headers:** `X-API-Key: <your_key>`
**Request Body:**
```json
{
  "url": "https://yourapp.com/events",
  "events": ["upload.completed", "playback.requested"]
}
```

### List Webhooks
`GET /v1/webhooks?owner=self`

### Delete Webhook
`DELETE /v1/webhooks/{webhook_id}`

---

## 1.5 System Metrics
`GET /v1/metrics`
Returns aggregate platform data including total video count, storage size in bytes, total duration, and system resource limits.

---

# 2. Data Plane APIs (Port 8001)

## 2.1 Chunk Upload & Resumption

### Get Upload Status (Resumable Uploads)
`GET /v1/upload-session/{session_id}`
Returns a list of already uploaded chunks so the client can resume safely.
**Response:**
```json
{
  "session": "uuid",
  "uploaded_chunks": [0, 1, 2, 5]
}
```

### Upload Chunk
`POST /v1/upload-chunk/{session_id}/chunk_{index}/{index}`
Uploads physical binary video data.
**Request:** `multipart/form-data` containing the file byte chunk.

---

## 2.2 Streaming

### Fetch Playlist / Video Segments
`GET /hls/{video_id}/{filename}`
Serves actual HLS streams (`.m3u8` and `.ts` files) from storage or Walrus.
Requires valid signature parameters derived from `/v1/playback-url`.
