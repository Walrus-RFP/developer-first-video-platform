import requests
import os
import math
import time
from typing import List, Optional, Dict, Any
from utils.logger import logger


class WalrusVideo:
    """
    Developer-first SDK for the decentralized video platform.
    Enables one-line uploads, resumable chunked transfers, and playback.
    """

    def __init__(
        self,
        api_key: str,
        api_base: str = "http://localhost:8000",
        data_plane: str = "http://localhost:8001",
    ):
        self.api_key = api_key
        self.api_base = api_base.rstrip("/")
        self.data_plane = data_plane.rstrip("/")

    # ── Upload ───────────────────────────────────────────────────────────────

    def upload_video(
        self,
        file_path: str,
        chunk_size: int = 5 * 1024 * 1024,  # 5 MB chunks
        title: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        is_public: bool = True,
        poll_timeout: int = 600,  # seconds
        parallel: int = 4,        # concurrent chunk uploads
    ) -> str:
        """
        Upload a video file in parallel chunks and return the video_id.
        Supports resumable uploads — skips chunks already stored on the server.
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        file_size = os.path.getsize(file_path)
        total_chunks = math.ceil(file_size / chunk_size)

        # 1. Create session
        headers = {"X-API-Key": self.api_key}
        sess_resp = requests.post(
            f"{self.api_base}/v1/upload-session", headers=headers, timeout=15
        ).json()
        session_id = sess_resp.get("upload_session_id")
        if not session_id:
            raise Exception(f"Failed to create upload session: {sess_resp}")

        # 2. Check which chunks are already uploaded (resume support)
        uploaded: set = set()
        try:
            status_resp = requests.get(
                f"{self.data_plane}/v1/upload-session/{session_id}", timeout=10
            )
            if status_resp.ok:
                uploaded = set(status_resp.json().get("uploaded_chunks", []))
                if uploaded:
                    logger.info(
                        "Resuming upload: %d/%d chunks already stored",
                        len(uploaded), total_chunks,
                        extra={"session_id": session_id},
                    )
        except Exception:
            pass

        # 3. Read all chunk data upfront (allows parallel upload without seeking conflicts)
        chunks: List[tuple] = []  # (index, data)
        with open(file_path, "rb") as f:
            for i in range(total_chunks):
                data = f.read(chunk_size)
                if i not in uploaded:
                    chunks.append((i, data))

        def _upload_chunk(idx_data: tuple) -> int:
            idx, data = idx_data
            files = {"file": (f"chunk_{idx}", data, "application/octet-stream")}
            for attempt in range(1, 4):
                resp = requests.post(
                    f"{self.data_plane}/v1/upload-chunk/{session_id}/chunk_{idx}/{idx}",
                    files=files,
                    timeout=120,
                )
                if resp.ok:
                    return idx
                if attempt == 3:
                    raise Exception(f"Chunk {idx} failed after 3 attempts: {resp.text}")
                time.sleep(0.5 * attempt)
            return idx  # unreachable

        completed = len(uploaded)
        with ThreadPoolExecutor(max_workers=parallel) as executor:
            futures = {executor.submit(_upload_chunk, item): item[0] for item in chunks}
            for future in as_completed(futures):
                future.result()  # raises on error
                completed += 1
                logger.info("Uploaded chunk %d/%d", completed, total_chunks)

        # 4. Kick off async completion
        params: Dict[str, Any] = {"is_public": str(is_public).lower()}
        if title:
            params["title"] = title
        if description:
            params["description"] = description
        if tags:
            params["tags"] = ",".join(tags)

        final_resp = requests.post(
            f"{self.api_base}/v1/complete-upload/{session_id}",
            params=params,
            headers=headers,
            timeout=15,
        )
        if not final_resp.ok:
            raise Exception(f"complete-upload failed: {final_resp.text}")

        # 5. Poll for completion with a hard timeout
        logger.info("Waiting for video processing...", extra={"session_id": session_id})
        deadline = time.time() + poll_timeout
        while time.time() < deadline:
            status_resp = requests.get(
                f"{self.api_base}/v1/upload-status/{session_id}", timeout=10
            )
            if status_resp.ok:
                data = status_resp.json()
                st = data.get("status", "")
                if st == "upload completed":
                    return data.get("video_id")
                elif st == "failed":
                    raise Exception(f"Video processing failed: {data.get('error')}")
                logger.info("Processing status: %s", st)
            time.sleep(3)

        raise TimeoutError(
            f"Video processing did not complete within {poll_timeout}s. "
            "Check backend logs for details."
        )

    # ── Playback ─────────────────────────────────────────────────────────────

    def get_playback_url(self, video_id: str, user_address: Optional[str] = None) -> str:
        """Get a signed playback URL, optionally gated by Sui on-chain permission."""
        params = {}
        if user_address:
            params["user_address"] = user_address
        resp = requests.get(
            f"{self.api_base}/v1/playback-url/{video_id}", params=params, timeout=10
        )
        if not resp.ok:
            raise Exception(f"Failed to get playback URL: {resp.text}")
        return resp.json()["playlist"]

    # ── Video Metadata ───────────────────────────────────────────────────────

    def get_video(self, video_id: str) -> Dict[str, Any]:
        resp = requests.get(f"{self.api_base}/v1/videos/{video_id}", timeout=10)
        resp.raise_for_status()
        return resp.json()

    def list_videos(self, owner: Optional[str] = None) -> List[Dict[str, Any]]:
        params = {"owner": owner} if owner else {}
        resp = requests.get(f"{self.api_base}/v1/videos", params=params, timeout=10)
        resp.raise_for_status()
        return resp.json().get("videos", [])

    def update_video(
        self,
        video_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        is_public: Optional[bool] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        if title is not None:
            payload["title"] = title
        if description is not None:
            payload["description"] = description
        if is_public is not None:
            payload["is_public"] = is_public
        headers = {"X-API-Key": self.api_key}
        resp = requests.patch(
            f"{self.api_base}/v1/videos/{video_id}", json=payload, headers=headers, timeout=10
        )
        resp.raise_for_status()
        return resp.json()

    def delete_video(self, video_id: str) -> bool:
        headers = {"X-API-Key": self.api_key}
        resp = requests.delete(
            f"{self.api_base}/v1/videos/{video_id}", headers=headers, timeout=10
        )
        return resp.status_code == 200

    # ── Webhooks ─────────────────────────────────────────────────────────────

    def register_webhook(self, url: str, events: List[str] = ["*"]) -> Dict[str, str]:
        """Register a webhook to receive platform events."""
        headers = {"X-API-Key": self.api_key}
        payload = {"url": url, "events": events}
        resp = requests.post(
            f"{self.api_base}/v1/webhooks", json=payload, headers=headers, timeout=10
        )
        resp.raise_for_status()
        return resp.json()

    def list_webhooks(self) -> List[Dict[str, Any]]:
        headers = {"X-API-Key": self.api_key}
        resp = requests.get(
            f"{self.api_base}/v1/webhooks", headers=headers, timeout=10
        )
        resp.raise_for_status()
        return resp.json()["webhooks"]

    def delete_webhook(self, webhook_id: str) -> bool:
        headers = {"X-API-Key": self.api_key}
        resp = requests.delete(
            f"{self.api_base}/v1/webhooks/{webhook_id}", headers=headers, timeout=10
        )
        return resp.status_code == 200

    # ── API Keys ─────────────────────────────────────────────────────────────

    def generate_api_key(self, name: str, owner: str) -> Dict[str, str]:
        payload = {"owner": owner, "name": name}
        resp = requests.post(
            f"{self.api_base}/v1/api-keys", json=payload, timeout=10
        )
        resp.raise_for_status()
        return resp.json()

    def list_api_keys(self, owner: str) -> List[Dict[str, str]]:
        resp = requests.get(
            f"{self.api_base}/v1/api-keys/{owner}", timeout=10
        )
        resp.raise_for_status()
        return resp.json()["api_keys"]

    # ── Analytics ────────────────────────────────────────────────────────────

    def get_video_analytics(self, video_id: str) -> Dict[str, Any]:
        """Per-video analytics: views, bandwidth, daily breakdown."""
        headers = {"X-API-Key": self.api_key}
        resp = requests.get(
            f"{self.api_base}/v1/videos/{video_id}/analytics", headers=headers, timeout=10
        )
        resp.raise_for_status()
        return resp.json()

    def get_embed(self, video_id: str, user_address: Optional[str] = None) -> Dict[str, Any]:
        """Get embed URL and iframe HTML for cross-application video reuse."""
        params = {}
        if user_address:
            params["user_address"] = user_address
        resp = requests.get(
            f"{self.api_base}/v1/videos/{video_id}/embed", params=params, timeout=10
        )
        resp.raise_for_status()
        return resp.json()

    # ── Webhook helpers ───────────────────────────────────────────────────────

    @staticmethod
    def verify_webhook_signature(payload: bytes, signature_header: str, secret: str) -> bool:
        """
        Verify an incoming webhook delivery from the platform.

        Usage in your receiver:
            raw_body = request.body()
            sig      = request.headers["X-Webhook-Signature"]
            valid    = WalrusVideo.verify_webhook_signature(raw_body, sig, YOUR_SIGNING_SECRET)
            if not valid:
                return 401

        Args:
            payload:          Raw request body bytes.
            signature_header: Value of the X-Webhook-Signature header (e.g. "sha256=abc123").
            secret:           Your SIGNING_SECRET (same value set on the platform).
        """
        import hashlib
        import hmac
        expected = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature_header)

    # ── Video Versioning ─────────────────────────────────────────────────────

    def create_video_version(
        self,
        new_video_id: str,
        parent_video_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        is_public: bool = True,
    ) -> Dict[str, Any]:
        """
        Register a new version of a video. Returns Sui transaction parameters
        for the caller to sign (video_registry::register_video_version on-chain).
        """
        headers = {"X-API-Key": self.api_key}
        payload: Dict[str, Any] = {"parent_video_id": parent_video_id, "is_public": is_public}
        if title is not None:
            payload["title"] = title
        if description is not None:
            payload["description"] = description
        resp = requests.post(
            f"{self.api_base}/v1/videos/{new_video_id}/version",
            json=payload,
            headers=headers,
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    # ── Subscription Policies ─────────────────────────────────────────────────

    def get_subscription_policy(self, video_id: str) -> Dict[str, Any]:
        """Get the on-chain subscription policy for a video."""
        resp = requests.get(f"{self.api_base}/v1/subscription/{video_id}", timeout=10)
        resp.raise_for_status()
        return resp.json()

    def create_subscription_policy(
        self,
        video_id: str,
        price_mist: int,
        duration_epochs: int,
        revenue_address: str,
    ) -> Dict[str, Any]:
        """
        Returns Sui transaction parameters for the caller to sign.
        The wallet executes access_control::set_subscription_policy on-chain.

        Args:
            price_mist:       Price in MIST (1 SUI = 1_000_000_000 MIST).
            duration_epochs:  How many Sui epochs the grant lasts.
            revenue_address:  SUI address that receives subscription payments.
        """
        headers = {"X-API-Key": self.api_key}
        payload = {
            "price_mist": price_mist,
            "duration_epochs": duration_epochs,
            "revenue_address": revenue_address,
        }
        resp = requests.post(
            f"{self.api_base}/v1/subscription/{video_id}",
            json=payload,
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    # ── Seal Policy ───────────────────────────────────────────────────────────

    # ── Seal Key Management ───────────────────────────────────────────────────

    def get_encryption_key(self, video_id: str) -> str:
        """
        One-time retrieval of the plaintext AES key for a private video.
        Call this immediately after upload to obtain the key for Seal-encryption.
        Returns the base64-encoded AES-GCM-256 key.
        Raises if the key has already been cleared (Seal setup already done).
        """
        headers = {"X-API-Key": self.api_key}
        resp = requests.get(
            f"{self.api_base}/v1/videos/{video_id}/encryption-key",
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()["encryption_key_b64"]

    def commit_seal_key(self, video_id: str, seal_key_blob_id: str) -> Dict[str, Any]:
        """
        Commit the Walrus blob ID of the Seal-encrypted AES key.
        Clears the plaintext key from the server permanently.
        After this call, only Seal SDK can distribute the key to authorised viewers.
        """
        headers = {"X-API-Key": self.api_key}
        resp = requests.post(
            f"{self.api_base}/v1/videos/{video_id}/seal-key",
            json={"seal_key_blob_id": seal_key_blob_id},
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def upload_seal_blob(self, encrypted_key_bytes: bytes) -> str:
        """
        Upload a Seal-encrypted key blob to Walrus via the data plane.
        Returns the blob_id to pass to commit_seal_key().
        """
        resp = requests.post(
            f"{self.data_plane}/v1/seal-blob",
            data=encrypted_key_bytes,
            headers={"Content-Type": "application/octet-stream"},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["blob_id"]

    def download_seal_blob(self, blob_id: str) -> bytes:
        """Download a Seal-encrypted key blob from Walrus via the data plane."""
        resp = requests.get(f"{self.data_plane}/v1/seal-blob/{blob_id}", timeout=30)
        resp.raise_for_status()
        return resp.content

    def link_seal_policy(self, video_id: str, seal_policy_id: str) -> Dict[str, Any]:
        """
        Returns Sui transaction parameters to link a Mysten Seal policy to a video.
        The caller must sign and execute the returned transaction.

        Seal flow:
          1. Deploy a Seal policy on Sui using the Mysten Seal SDK/CLI.
          2. Call this method with the resulting seal_policy_id (Sui object ID).
          3. Sign the returned transaction with your Sui wallet.
          4. Decryption keys will be distributed via Seal for authorised viewers.
             AES-GCM remains active as a fallback for legacy clients.
        """
        headers = {"X-API-Key": self.api_key}
        resp = requests.post(
            f"{self.api_base}/v1/videos/{video_id}/seal-policy",
            json={"seal_policy_id": seal_policy_id},
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def get_seal_policy(self, video_id: str) -> Dict[str, Any]:
        """Get the Seal policy linked to a video, if any."""
        resp = requests.get(f"{self.api_base}/v1/videos/{video_id}/seal-policy", timeout=10)
        resp.raise_for_status()
        return resp.json()

    # ── Metrics ──────────────────────────────────────────────────────────────

    def get_metrics(self) -> Dict[str, Any]:
        resp = requests.get(f"{self.api_base}/v1/metrics", timeout=10)
        resp.raise_for_status()
        return resp.json()


# ── Example usage ─────────────────────────────────────────────────────────────
# sdk = WalrusVideo(api_key="cv_...", api_base="http://localhost:8000")
# video_id = sdk.upload_video("demo.mp4", title="My First Video")
# url = sdk.get_playback_url(video_id, user_address="0xabc...")
