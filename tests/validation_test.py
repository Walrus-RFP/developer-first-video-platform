import sys
from utils.sdk import WalrusVideo

def test_invalid():
    sdk = WalrusVideo(api_key="cv_kZ189rWJ6tlXx39MdLup7vAeIpLUlkPRTdGhyuqcWsE", api_base="http://control-plane:8000")
    sdk.data_plane = "http://data-plane:8001"
    try:
        sdk.upload_video("invalid.txt")
        print("FAILED: Accepted invalid file")
    except Exception as e:
        print(f"SUCCESS: Caught error: {e}")

if __name__ == "__main__":
    test_invalid()
