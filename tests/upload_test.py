import requests
import os
import math

CONTROL_PLANE_URL = "http://127.0.0.1:8000"
DATA_PLANE_URL = "http://127.0.0.1:8001"
CHUNK_SIZE = 1024 * 1024 * 2  # 2MB chunks

def test_large_upload():
    print("--- Testing Large Chunked Upload ---")
    test_file = "test.mp4"
    
    if not os.path.exists(test_file):
        print("Missing test.mp4")
        return
        
    file_size = os.path.getsize(test_file)
    print(f"Found {file_size} bytes text file.")
    
    try:
        # 1. Start Session
        resp = requests.post(f"{CONTROL_PLANE_URL}/upload-session")
        session_id = resp.json()["upload_session_id"]
        print(f"Session started: {session_id}")
        
        # 2. Upload Chunks
        total_chunks = math.ceil(file_size / CHUNK_SIZE)
        print(f"Uploading {total_chunks} chunks...")
        
        with open(test_file, "rb") as f:
            for i in range(total_chunks):
                chunk_data = f.read(CHUNK_SIZE)
                if not chunk_data: break
                chunk_id = f"chunk_{i:03d}"
                print(f"  -> Uploading {chunk_id} ({len(chunk_data)} bytes)")
                
                res = requests.post(
                    f"{DATA_PLANE_URL}/upload-chunk/{session_id}/{chunk_id}/{i}",
                    files={"file": chunk_data}
                )
                if res.status_code != 200:
                    print(f"❌ Failed to upload {chunk_id}: {res.text}")
                    return
        
        # 3. Complete Upload
        print("Completing upload and merging...")
        resp = requests.post(f"{CONTROL_PLANE_URL}/complete-upload/{session_id}")
        result = resp.json()
        print(f"Final response: {result}")
        
        if "video_id" in result:
             print("\n✅ SUCCESS: Large file chunked upload completed successfully.")
        else:
             print("\n❌ FAILURE: Upload completion did not return a video_id")
             
    finally:
        os.remove(test_file)

if __name__ == "__main__":
    test_large_upload()
