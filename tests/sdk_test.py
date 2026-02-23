import os
import time
from utils.sdk import WalrusVideo

def main():
    print("Testing WalrusVideo SDK...")
    
    # 1. Generate an API Key (in prod, this is done via dashboard/admin api)
    import requests
    resp = requests.post("http://localhost:8000/v1/api-keys", json={
        "owner": "0xTestUser",
        "name": "Integration Test Key"
    })
    
    if not resp.ok:
        print(f"Failed to generate API Key: {resp.text}")
        return
        
    api_key_data = resp.json()
    api_key = api_key_data["api_key"]
    print(f"Generated API Key: {api_key}")

    # 2. Initialize SDK
    sdk = WalrusVideo(api_key=api_key, api_base="http://localhost:8000")
    sdk.data_plane = "http://localhost:8001"

    # 3. Complete Upload
    video_path = "test_video.mp4"
    if not os.path.exists(video_path):
        print(f"Error: {video_path} not found.")
        return

    print("Uploading video...")
    start_time = time.time()
    try:
        video_id = sdk.upload_video(video_path, title="SDK Test Video", chunk_size=1024*1024)
        print(f"Upload complete! Video ID: {video_id}")
        print(f"Time taken: {time.time() - start_time:.2f} seconds")
    except Exception as e:
        print(f"Upload failed: {e}")
        return

    # 4. Check Playback URL
    print("Generating playback URL...")
    try:
        playback_data = sdk.get_playback_url(video_id)
        print(f"Playback data: {playback_data}")
    except Exception as e:
        print(f"Failed to get playback url: {e}")

    # 5. Check Video Metadata
    print("Fetching video metadata...")
    try:
        metadata = sdk.get_video(video_id)
        print(f"Metadata: {metadata}")
    except Exception as e:
        print(f"Failed to fetch metadata: {e}")

if __name__ == "__main__":
    main()
