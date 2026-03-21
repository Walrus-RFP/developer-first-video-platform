# Metadata Schema

The metadata schema defines how video assets are stored and tracked in the Control Plane database. The system uses **SQLite** for local development (default: `video_metadata.db`) and **PostgreSQL** in production (configured via the `DATABASE_URL` environment variable).

## `videos` Table

| Field Name | Type | Description |
|------------|------|-------------|
| `video_id` | VARCHAR (PRIMARY KEY) | A unique UUID representing the video asset. |
| `owner` | VARCHAR | The Sui wallet address or identifier of the user/application that owns the video. |
| `file_path` | VARCHAR | The local path to the finalized `.mp4` file (used as a fallback reference). |
| `version` | INTEGER | The version number of the video asset. Supports versioned asset updates. |
| `status` | VARCHAR | Current processing status (e.g., `uploaded`, `processing`, `upload completed`, `failed`). |
| `created_at` | VARCHAR | ISO-8601 timestamp of when the upload record was created. |
| `updated_at` | VARCHAR | ISO-8601 timestamp of the last metadata update. |
| `checksum` | VARCHAR | SHA-256 hash of the final merged video file. Used for deduplication. |
| `title` | VARCHAR | Human-readable title set at upload time or updated via PATCH. |
| `description` | VARCHAR | Optional description of the video. |
| `tags` | VARCHAR | JSON array of string tags (e.g. `["tutorial","web3"]`). |
| `duration_seconds` | REAL | Video duration in seconds extracted by FFmpeg during HLS transcoding. |
| `resolution` | VARCHAR | Detected resolution of the source file (e.g. `1920x1080`). |
| `file_size` | INTEGER | Size of the source file in bytes. |
| `is_public` | INTEGER | `1` = publicly accessible; `0` = requires on-chain access check via Sui. |
| `encryption_key` | VARCHAR | Plaintext AES-GCM-256 key (only present before Seal setup; cleared after). |
| `seal_key_blob_id` | VARCHAR | Walrus blob ID of the Seal-encrypted AES key for threshold decryption. |
| `content_hash` | VARCHAR | Deduplication hash of the raw upload content. |

## `api_keys` Table

| Field Name | Type | Description |
|------------|------|-------------|
| `key` | VARCHAR (PRIMARY KEY) | The API key value (prefixed `cv_`). |
| `owner` | VARCHAR | The wallet address or identifier of the key owner. |
| `name` | VARCHAR | Human-readable label for the key. |
| `created_at` | VARCHAR | ISO-8601 creation timestamp. |
| `revoked` | INTEGER | `0` = active; `1` = revoked. |

## `upload_sessions` Table

Tracks asynchronous background upload/processing jobs, replacing the previous in-memory state.

| Field Name | Type | Description |
|------------|------|-------------|
| `session_id` | VARCHAR (PRIMARY KEY) | UUID of the upload session. |
| `status` | VARCHAR | `queued`, `processing`, `upload completed`, or `failed`. |
| `video_id` | VARCHAR | The resulting `video_id` once processing completes. |
| `error` | VARCHAR | Error message if status is `failed`. |
| `playlist` | VARCHAR | The signed HLS playlist URL returned to the client on completion. |
| `sui_package_id` | VARCHAR | The deployed Sui package ID (echoed back for client convenience). |
| `sui_registry_id` | VARCHAR | The shared Registry object ID. |
| `owner` | VARCHAR | Owner identifier carried through from the upload request. |
| `created_at` | VARCHAR | ISO-8601 creation timestamp. |
| `updated_at` | VARCHAR | ISO-8601 last-updated timestamp. |

## `usage_logs` Table

Append-only log of ingress/egress events, used for analytics and bandwidth metrics.

| Field Name | Type | Description |
|------------|------|-------------|
| `id` | SERIAL / AUTOINCREMENT | Auto-incrementing row ID. |
| `video_id` | VARCHAR | Video that was accessed. |
| `owner` | VARCHAR | Owner of the video. |
| `user_address` | VARCHAR | Viewer's Sui wallet address (nullable). |
| `type` | VARCHAR | `ingress` (upload) or `egress` (playback). |
| `bytes` | BIGINT | Bytes transferred in this event. |
| `timestamp` | VARCHAR | ISO-8601 timestamp. |

## Asset Reuse / Deduplication

When a new file finishes uploading, the Control Plane generates its SHA-256 checksum. Before creating a new `video_id`, the system checks the `videos` table for an existing matching `checksum`. If found, the existing `video_id` and playlist URL are returned immediately — avoiding redundant storage and processing.
