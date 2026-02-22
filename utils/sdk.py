import requests
import os
import math

class WalrusVideo:
    """
    Developer-first SDK for the Decentralized Video Platform.
    Enables one-line uploads and playback authorization.
    """
    def __init__(self, api_base="http://localhost:8000"):
        self.api_base = api_base
        self.data_plane = "http://localhost:8001" # Default data plane Port

    def upload_video(self, file_path: str, chunk_size=1024*1024*2):
        """
        Uploads a video file in chunks and returns the video_id.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        file_size = os.path.getsize(file_path)
        total_chunks = math.ceil(file_size / chunk_size)

        # 1. Create session
        sess_resp = requests.post(f"{self.api_base}/upload-session").json()
        session_id = sess_resp["upload_session_id"]

        # 2. Upload chunks
        with open(file_path, "rb") as f:
            for i in range(total_chunks):
                chunk = f.read(chunk_size)
                files = {"file": chunk}
                requests.post(
                    f"{self.data_plane}/upload-chunk/{session_id}/chunk_{i}/{i}",
                    files=files
                )
                print(f"Uploaded chunk {i+1}/{total_chunks}")

        # 3. Complete upload
        final_resp = requests.post(f"{self.api_base}/complete-upload/{session_id}").json()
        return final_resp["video_id"]

    def get_playback_url(self, video_id: str, user_address: str = None):
        """
        Gets a signed playback URL, optionally checking Sui permissions.
        """
        params = {"user_address": user_address} if user_address else {}
        resp = requests.get(f"{self.api_base}/playback-url/{video_id}", params=params)
        
        if resp.status_code != 200:
            raise Exception(f"Failed to get playback URL: {resp.text}")
            
        return resp.json()["playlist"]

# Example Usage:
# sdk = WalrusVideo()
# vid = sdk.upload_video("my_movie.mp4")
# url = sdk.get_playback_url(vid, user_address="0xabc...")
