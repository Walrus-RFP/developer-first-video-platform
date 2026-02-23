# Walrus Platform: Developer-First Video Infrastructure

A decentralized, developer-first video platform built on **Sui** and the **Walrus** decentralized storage network. It provides a complete end-to-end pipeline for uploading, processing (HLS), storing, and streaming videos with on-chain access control.

## 🏗️ Architecture Overview

The platform is split into two microservices to ensure stability under load:

1. **Control Plane (Port 8000):** 
   - Handles metadata, database operations (SQLite), API keys, webhook event dispatching, and Sui smart contract interactions.
   - Routes: `/v1/upload-session`, `/v1/complete-upload`, `/v1/videos`, `/v1/webhooks`, `/v1/api-keys`, `/v1/metrics`.
   - **Authentication**: Secured via `X-API-Key` headers.

2. **Data Plane (Port 8001):**
   - Handles heavy lifting: receiving video chunks, merging, streaming HLS playlists, and reading/writing to the Walrus network.
   - Routes: `/v1/upload-chunk`, `/v1/manifest`, `/v1/upload-session/{id}`, `/hls` (playback).
   - Validates signed URLs before streaming private video segments.

---

## 🚀 Quick Start (Local Development)

### Prerequisites
- Python 3.9+
- `ffmpeg` installed (macOS: `brew install ffmpeg`, Ubuntu: `sudo apt install ffmpeg`)
- Sui CLI (Optional, used for local contract deployment)

### 1. Setup Environment
```bash
# Clone the repository
git clone https://github.com/Walrus-RFP/developer-first-video-platform.git
cd developer-first-video-platform

# Create Python environment
python -m venv venv
source venv/bin/activate  # Windows: venv\\Scripts\\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy the `.env.example` to `.env` and fill in the values:
```bash
cp .env.example .env
```
Ensure `WALRUS_AGGREGATOR` and `WALRUS_PUBLISHER` are set to valid network nodes.

### 3. Run the Services
Open two terminal windows (ensure the `venv` is active in both).

**Terminal 1 (Control Plane):**
```bash
uvicorn control_plane.main:app --reload --port 8000
```

**Terminal 2 (Data Plane):**
```bash
uvicorn data_plane.stream_server:app --reload --port 8001
```

### 4. Run the Frontend (Next.js)
```bash
cd frontend
npm install
npm run dev
```
Visit `http://localhost:3000` to see the UI.

---

## 💻 Developer SDK (Python)

We provide a specialized SDK (`utils/sdk.py`) to make interacting with the platform trivial.

### Initialization
```python
from utils.sdk import WalrusVideo

# Initialize with your API Key
sdk = WalrusVideo(api_key="cv_your_api_key_here")
```

### Video Management
```python
# Upload a new video (supports resumable chunking automatically)
video_id = sdk.upload_video(
    file_path="my_movie.mp4", 
    title="My First Video",
    is_public=False # Set to True for free viewing, False for Sui-gated viewing
)

# Get a signed playback URL (enforces on-chain checks for private videos)
playlist_url = sdk.get_playback_url(video_id, user_address="0x123...")

# Update metadata
sdk.update_video(video_id, title="Updated Title", is_public=True)

# Fetch metadata
metadata = sdk.get_video(video_id)
```

### Webhooks
Listen to platform events like `upload.completed` or `playback.requested`.
```python
# Register a webhook
webhook = sdk.register_webhook(url="https://myapp.com/webhook", events=["upload.completed"])

# List webhooks
print(sdk.list_webhooks())
```

### Platform Metrics
```python
# Get total storage, duration, and video count
metrics = sdk.get_metrics()
print(metrics)
```

---

## 🔒 Security & Rate Limiting
- **API Keys**: Required for all modifying actions. Pass via the `X-API-Key` HTTP header.
- **Rate Limiting / Analytics**: Strict rate limits + real-time ingress/egress bandwidth tracking.
- **Sui Smart Contracts**: Hard-gated access control. `/playback-url` queries the Sui network via JSON-RPC (`sui_devInspectTransactionBlock`) to verify a user's on-chain viewing rights before generating signed URLs for private videos.