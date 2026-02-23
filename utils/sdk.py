import requests
import os
import math
from typing import List, Optional, Dict, Any
from utils.logger import logger

class WalrusVideo:
    """
    Developer-first SDK for the Decentralized Video Platform.
    Enables one-line uploads and playback authorization.
    """
    def __init__(self, api_key: str, api_base="http://localhost:8000"):
        self.api_key = api_key
        self.api_base = api_base
        self.data_plane = "http://localhost:8001" # Default data plane Port

    def upload_video(self, file_path: str, chunk_size=1024*1024*2, title: str = None, is_public: bool = True):
        """
        Uploads a video file in chunks and returns the video_id.
        Supports resumable uploads — skips chunks already on the server.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        file_size = os.path.getsize(file_path)
        total_chunks = math.ceil(file_size / chunk_size)

        # 1. Create session
        headers = {"X-API-Key": self.api_key}
        sess_resp = requests.post(f"{self.api_base}/v1/upload-session", headers=headers).json()
        session_id = sess_resp.get("upload_session_id")
        if not session_id:
            raise Exception(f"Failed to create upload session: {sess_resp}")

        # 2. Check which chunks are already uploaded (resume support)
        uploaded = set()
        try:
            status_resp = requests.get(f"{self.data_plane}/v1/upload-session/{session_id}")
            if status_resp.ok:
                uploaded = set(status_resp.json().get("uploaded_chunks", []))
                if uploaded:
                    logger.info("Resuming upload", extra={
                        "session_id": session_id,
                        "uploaded_count": len(uploaded),
                        "total_chunks": total_chunks
                    })
        except Exception:
            pass

        # 3. Upload remaining chunks
        with open(file_path, "rb") as f:
            for i in range(total_chunks):
                chunk = f.read(chunk_size)
                if i in uploaded:
                    logger.debug("Skipping chunk (already uploaded)", extra={
                        "chunk_index": i,
                        "total_chunks": total_chunks
                    })
                    continue
                files = {"file": chunk}
                requests.post(
                    f"{self.data_plane}/v1/upload-chunk/{session_id}/chunk_{i}/{i}",
                    files=files
                )
                logger.info("Uploaded chunk", extra={
                    "chunk_index": i,
                    "total_chunks": total_chunks
                })

        # 4. Kick off async completion
        params = {"is_public": is_public}
        if title:
            params["title"] = title
        headers = {"X-API-Key": self.api_key}
        final_resp = requests.post(f"{self.api_base}/v1/complete-upload/{session_id}", params=params, headers=headers).json()
        
        # 5. Poll for video_id
        import time
        logger.info("Waiting for video processing...", extra={"session_id": session_id})
        while True:
            status_resp = requests.get(f"{self.api_base}/v1/upload-status/{session_id}")
            if status_resp.ok:
                data = status_resp.json()
                if data.get("status") == "upload completed":
                    return data.get("video_id")
                elif data.get("status") == "failed":
                    raise Exception(f"Video processing failed: {data.get('error')}")
                
                logger.info("Processing status: %s", data.get("status"))
            
            time.sleep(2)

    def get_playback_url(self, video_id: str, user_address: str = None):
        """
        Gets a signed playback URL, optionally checking Sui permissions.
        """
        params = {"user_address": user_address} if user_address else {}
        resp = requests.get(f"{self.api_base}/v1/playback-url/{video_id}", params=params)
        
        if resp.status_code != 200:
            raise Exception(f"Failed to get playback URL: {resp.text}")
            
        return resp.json()["playlist"]

    # --- VIDEO METADATA ---
    
    def get_video(self, video_id: str) -> Dict[str, Any]:
        """Fetch metadata for a specific video."""
        resp = requests.get(f"{self.api_base}/v1/videos/{video_id}")
        resp.raise_for_status()
        return resp.json()

    def update_video(self, video_id: str, title: str = None, description: str = None, is_public: bool = None) -> Dict[str, Any]:
        """Update metadata on an existing video."""
        payload = {}
        if title is not None: payload["title"] = title
        if description is not None: payload["description"] = description
        if is_public is not None: payload["is_public"] = is_public
        
        headers = {"X-API-Key": self.api_key}
        resp = requests.patch(f"{self.api_base}/v1/videos/{video_id}", json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()

    # --- WEBHOOKS ---

    def register_webhook(self, url: str, events: List[str] = ["*"]) -> Dict[str, str]:
        """Register a webhook to receive platform events (e.g., upload.completed)."""
        headers = {"X-API-Key": self.api_key}
        payload = {"url": url, "events": events, "owner": "self"}
        resp = requests.post(f"{self.api_base}/v1/webhooks", json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()

    def list_webhooks(self) -> List[Dict[str, Any]]:
        """List all active webhooks for this account."""
        headers = {"X-API-Key": self.api_key}
        resp = requests.get(f"{self.api_base}/v1/webhooks?owner=self", headers=headers)
        resp.raise_for_status()
        return resp.json()["webhooks"]

    def delete_webhook(self, webhook_id: str) -> bool:
        """Delete a registered webhook by ID."""
        headers = {"X-API-Key": self.api_key}
        resp = requests.delete(f"{self.api_base}/v1/webhooks/{webhook_id}", headers=headers)
        return resp.status_code == 200

    # --- API KEYS ---

    def generate_api_key(self, name: str) -> Dict[str, str]:
        """Generate a new Developer API Key."""
        headers = {"X-API-Key": self.api_key}
        # Assuming the backend trusts the current valid key's owner for this operation
        # In a real system, the owner ID would be extracted via the backend, but we pass dummy owner for now.
        payload = {"owner": "self", "name": name}
        resp = requests.post(f"{self.api_base}/v1/api-keys", json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()

    def list_api_keys(self) -> List[Dict[str, str]]:
        """List all API keys belonging to the account."""
        headers = {"X-API-Key": self.api_key}
        resp = requests.get(f"{self.api_base}/v1/api-keys/self", headers=headers)
        resp.raise_for_status()
        return resp.json()["api_keys"]

    # --- METRICS ---

    def get_metrics(self) -> Dict[str, Any]:
        """Get aggregate platform metrics (storage used, video count, etc.)"""
        resp = requests.get(f"{self.api_base}/v1/metrics")
        resp.raise_for_status()
        return resp.json()

# Example Usage:
# sdk = WalrusVideo()
# vid = sdk.upload_video("my_movie.mp4")
# url = sdk.get_playback_url(vid, user_address="0xabc...")
