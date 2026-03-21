# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Local Development (Docker)
```bash
cp .env.example .env          # Fill in real values (see env vars section)
docker compose up --build     # Start all services
docker compose down           # Stop all services
docker compose logs -f        # Tail all service logs
```

### Running Services Individually
```bash
# Install Python deps
pip install -r requirements.txt

# Control Plane (port 8000)
uvicorn control_plane.main:app --reload --port 8000

# Data Plane (port 8001)
uvicorn data_plane.stream_server:app --reload --port 8001

# Frontend (port 3000)
cd frontend && npm install && npm run dev

# Sui Auth Proxy (port 8002)
cd sui-auth-proxy && npm install && node index.js
```

### Tests
Integration tests require running services (control plane :8000, data plane :8001):
```bash
pytest tests/                      # All integration tests
pytest tests/test_upload.py        # Upload pipeline tests
pytest tests/test_playback.py      # Playback + signed URL tests
pytest tests/test_walrus.py        # Walrus storage roundtrip tests
pytest tests/test_upload.py::TestRateLimit  # Single test class
```
Tests skip gracefully when services are not running. Requires `tests/assets/test_video.mp4` for chunk upload tests.

### Smart Contracts (Move 2024 / Sui)
```bash
cd smart_contracts
sui move build
sui move test
sui client publish --gas-budget 100000000   # Deploy to testnet
```
After deploying, set `SUI_PACKAGE_ID`, `SUI_REGISTRY_ID`, `SUI_ACCESS_STORE_ID` in `.env`.
Get the object IDs from the publish output or `sui client object <digest>`.

## Architecture

Developer-first video platform on Sui + Walrus. Clear split between control (metadata/orchestration) and data (streaming/blobs).

### Service Map

| Service | Port | Language | Role |
|---------|------|----------|------|
| Control Plane | 8000 | Python/FastAPI | Upload sessions, metadata, API keys, webhooks |
| Data Plane | 8001 | Python/FastAPI | Chunk upload, HLS serving, Walrus blob retrieval |
| Frontend | 3000 | Next.js/TypeScript | Dashboard, video player, Sui wallet UI |
| Sui Auth Proxy | 8002 | Node.js/Express | Calls devInspectTransactionBlock for on-chain auth |

### Key Data Flows

**Upload:**
1. `POST /v1/upload-session` (Control Plane) → creates DB record + session dir
2. `POST /v1/upload-chunk/{session}/{id}/{index}` (Data Plane) → stores blob to Walrus, writes manifest.json with file lock
3. `POST /v1/complete-upload/{session}` (Control Plane) → kicks off BackgroundTask
4. Background: fetch manifest → read blobs → reassemble MP4 → FFmpeg HLS → upload HLS to Walrus (epochs=200) → write DB
5. Frontend: poll `/v1/upload-status/{session}` → on success, sign on-chain `register_video` tx

**Playback:**
1. `GET /v1/playback-url/{video_id}` → verifies owner or calls sui-auth-proxy → returns HMAC-signed URL
2. Data Plane: verify HMAC, look up blob_id from manifest, hit ChunkCache (RAM→disk→Walrus)
3. Playlists get `Cache-Control: no-store`; `.ts` segments get `immutable`

### Smart Contracts (two modules)

- `video_registry.move` — `Registry` shared object, ownership, versioning, Seal policy link
- `access_control.move` — `AccessStore` shared object, time-limited grants, subscription policies with SUI payment

`is_authorized(registry, store, video_id, user)` is the auth gate, called read-only via devInspectTransactionBlock.

### Storage Layers

| Layer | What | Where |
|-------|------|-------|
| Metadata | video rows, API keys, usage logs, upload sessions | PostgreSQL (SQLite in dev) |
| Upload chunks | raw MP4 chunks | Walrus testnet (`epochs=5`, temporary) |
| HLS assets | .ts segments, .m3u8 playlists, thumbnail | Walrus testnet (`epochs=200`, long-lived) |
| Cache | hot blobs | RAM (500 MB LRU, thread-safe) + disk (2 GB LRU) |
| Local fallback | HLS files for same-host deployments | `./storage/hls/{video_id}/` |

### Shared Utilities (`utils/`)

- `walrus.py` — accepts both `WALRUS_PUBLISHER/AGGREGATOR` (docker) and `PUBLISHER_URL/AGGREGATOR_URL` env vars; 30s timeout on all requests; fast-fails on 404 (blob permanently gone); retries transient errors
- `signing.py` — HMAC-SHA256 signed URLs; encryption key embedded in signature for stateless decryption
- `crypto.py` — AES-GCM-256; nonce prepended to ciphertext
- `sui.py` — HTTP client to sui-auth-proxy; returns `False` safely when contracts not deployed
- `sdk.py` — `WalStream` class; supports resumable chunked upload with 600s poll timeout

### Environment Variables

All variables with defaults are safe for local dev. Required for production:

| Variable | Used by | Notes |
|----------|---------|-------|
| `SIGNING_SECRET` | control + data plane | HMAC key; generate with `secrets.token_hex(32)` |
| `WALRUS_PUBLISHER` | walrus.py | Testnet: `https://publisher.walrus-testnet.walrus.space` |
| `WALRUS_AGGREGATOR` | walrus.py | Testnet: `https://aggregator.walrus-testnet.walrus.space` |
| `SUI_PACKAGE_ID` | sui.py, docker | Set after `sui client publish` |
| `SUI_REGISTRY_ID` | sui.py, docker | Shared Registry object ID |
| `SUI_ACCESS_STORE_ID` | sui-auth-proxy | Shared AccessStore object ID |
| `SUI_NETWORK` | sui-auth-proxy | `testnet` or `mainnet` |
| `PUBLIC_DATA_PLANE_URL` | signing.py | Embedded in playback URLs returned to clients |
| `WALRUS_HLS_EPOCHS` | upload.py | Default `50` (testnet max is ~53 epochs; mainnet supports higher values) |
| `WALRUS_CHUNK_EPOCHS` | chunk_upload.py | Default `5` (temporary raw chunks) |
