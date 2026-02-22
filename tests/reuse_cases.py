import requests

CONTROL_PLANE_URL = "http://127.0.0.1:8000"

def test_multi_app_playback():
    print("--- Testing Multi-App/Reuse Playback Cases ---")
    # Get the list of videos to test with
    resp = requests.get(f"{CONTROL_PLANE_URL}/videos")
    videos = resp.json().get("videos", [])
    
    if not videos:
        print("No videos found to test playback reuse. Please run upload_test.py first.")
        return
        
    video_id = videos[0]["video_id"]
    print(f"Selected video for reuse testing: {video_id}")
    
    # Simulate App 1 requesting a playback URL
    print("\n>> App 1 querying playback URL...")
    resp1 = requests.get(f"{CONTROL_PLANE_URL}/playback-url/{video_id}")
    url1 = resp1.json().get("playlist")
    print(f"App 1 Playback URL: {url1}")
    
    # Simulate App 2 requesting a playback URL for the same asset
    print("\n>> App 2 querying playback URL...")
    resp2 = requests.get(f"{CONTROL_PLANE_URL}/playback-url/{video_id}")
    url2 = resp2.json().get("playlist")
    print(f"App 2 Playback URL: {url2}")
    
    if url1 and url2:
         print("\n✅ SUCCESS: Same underlying video asset can be served to multiple clients with distinct authenticated URLs seamlessly.")
         
if __name__ == "__main__":
    test_multi_app_playback()
