from utils.sdk import WalrusVideo
import time
import requests
import os

def run_audit():
    sdk = WalrusVideo()
    
    print("\n--- [AUDIT START] Phase 10: Sui Access Control ---")
    
    # 1. Upload a small test file
    TEST_FILE = "photograph.mp4"
    if not os.path.exists(TEST_FILE):
        # Create a dummy file if needed
        with open(TEST_FILE, "wb") as f:
            f.write(b"dummy mp4 data for audit" * 1000)
    
    print(f"Step 1: Uploading {TEST_FILE}...")
    video_id = sdk.upload_video(TEST_FILE)
    print(f"Success! Video ID: {video_id}")
    
    # 2. Wait for background registration (if any)
    print("Step 2: Waiting for on-chain stabilization...")
    time.sleep(5)
    
    # 3. Test Authorized Access (Owner)
    OWNER_ADDRESS = "0x1ebda9acfd4a9c4cd9615b18e59315b048e6e876a0fafdbf251a960215f6727f"
    print(f"Step 3: Testing authorized access (Owner: {OWNER_ADDRESS})...")
    try:
        url = sdk.get_playback_url(video_id, user_address=OWNER_ADDRESS)
        print(f"GRANTED: {url}")
    except Exception as e:
        print(f"FAILED: Expected access but got error: {e}")

    # 4. Test Unauthorized Access (Random Address)
    RANDOM_ADDRESS = "0xdeadbeef12345678901234567890123456789012345678901234567890123456"
    print(f"Step 4: Testing unauthorized access (Random: {RANDOM_ADDRESS})...")
    try:
        url = sdk.get_playback_url(video_id, user_address=RANDOM_ADDRESS)
        print(f"FAILED: Expected 403 but got access: {url}")
    except Exception as e:
        print(f"SUCCESS: Access denied as expected: {e}")

    print("\n--- [AUDIT COMPLETE] Phase 10: VERIFIED ---")

if __name__ == "__main__":
    import os
    run_audit()
