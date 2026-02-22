import requests
import os
import time

CONTROL_PLANE_URL = "http://127.0.0.1:8000"
DATA_PLANE_URL = "http://127.0.0.1:8001"

def upload_file(file_path: str):
    print(f"--- Uploading {file_path} ---")
    
    # 1. Create Session
    resp = requests.post(f"{CONTROL_PLANE_URL}/upload-session")
    session_data = resp.json()
    session_id = session_data["upload_session_id"]
    print(f"Session ID: {session_id}")
    
    # 2. Upload Chunk
    with open(file_path, "rb") as f:
        file_data = f.read()
    
    print("Uploading chunk...")
    resp = requests.post(
        f"{DATA_PLANE_URL}/upload-chunk/{session_id}/chunk_001/0",
        files={"file": file_data}
    )
    print(f"Chunk upload status: {resp.status_code}")
    
    # 3. Complete Upload
    print("Completing upload...")
    resp = requests.post(f"{CONTROL_PLANE_URL}/complete-upload/{session_id}")
    result = resp.json()
    print(f"Complete upload response: {result}")
    return result

def test_reuse():
    test_file = "test.mp4"
    if not os.path.exists(test_file):
        print(f"File {test_file} not found. Please provide a valid test.mp4 file.")
        return
        
    try:
        # Upload 1
        print(">> First Upload (Should be a new asset)")
        res1 = upload_file(test_file)
        
        time.sleep(1)
        
        # Upload 2
        print("\n>> Second Upload (Should reuse existing asset)")
        res2 = upload_file(test_file)
        
        if res2.get("status") == "reused existing asset" and res1.get("video_id") == res2.get("video_id"):
            print("\n✅ SUCCESS: Asset reuse worked correctly!")
        else:
            print("\n❌ FAILURE: Asset reuse did not trigger or video_ids don't match.")
    except Exception as e:
        print(f"Error: {e}")
        # Upload 1
        print(">> First Upload (Should be a new asset)")
        res1 = upload_file(test_file)
        
        time.sleep(1)
        
        # Upload 2
        print("\n>> Second Upload (Should reuse existing asset)")
        res2 = upload_file(test_file)
        
        if res2.get("status") == "reused existing asset" and res1.get("video_id") == res2.get("video_id"):
            print("\n✅ SUCCESS: Asset reuse worked correctly!")
        else:
            print("\n❌ FAILURE: Asset reuse did not trigger or video_ids don't match.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_reuse()
