# Metadata Schema

The metadata schema defines how video assets are stored and tracked in the Control Plane database (`video_metadata.db`). The system uses SQLite to store the metadata.

## `videos` Table

| Field Name | Type | Description |
|------------|------|-------------|
| `video_id` | TEXT (PRIMARY KEY) | A unique UUID representing the video asset. |
| `owner`    | TEXT | The identifier of the user or application that owns the video. |
| `file_path`| TEXT | The local path to the finalized `.mp4` video file in the `uploads/` directory. |
| `version`  | INTEGER | The version number of the video asset. Used to support versioned asset updates. |
| `status`   | TEXT | Current status of the asset (e.g., `uploaded`). |
| `created_at`| TEXT | ISO-8601 formatted timestamp of when the upload was completed. |
| `checksum` | TEXT | SHA-256 hash of the final merged video file. Used to identify duplicate uploads for asset reuse. |

## Asset Reuse Mechanism

When a new file finishes uploading, the Control Plane generates its SHA-256 checksum. Before creating a new `video_id` and storing the file, the system checks the `videos` table using the `checksum`. If a matching record is found, the system immediately returns the existing `video_id` and playlist URL instead of processing the identical file, effectively deduplicating storage and fulfilling the "reusable asset" requirement.
