import os
import tempfile
import subprocess
import json
import uuid
import time
import functools

def with_retries(max_retries=3, initial_backoff=1):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            retries = 0
            backoff = initial_backoff
            while retries < max_retries:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    retries += 1
                    if retries >= max_retries:
                        print(f"[RETRY ERROR] Final failure after {max_retries} attempts: {e}")
                        raise
                    print(f"[RETRY WARNING] Attempt {retries} failed: {e}. Retrying in {backoff}s...")
                    time.sleep(backoff)
                    backoff *= 2
        return wrapper
    return decorator

@with_retries(max_retries=5, initial_backoff=2)
def store_blob(data: bytes, epochs: int = 1) -> str:
    """
    Stores a blob in Walrus using the local CLI via subprocess.
    Returns the newly created blob_id as a string.
    """
    tmp_path = os.path.join(tempfile.gettempdir(), f"walrus_upload_{uuid.uuid4().hex}")
    try:
        with open(tmp_path, "wb") as f:
            f.write(data)
            
        cmd = ["walrus", "--json", "store", "--epochs", str(epochs), tmp_path]
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        
        # The CLI dumps traces to stdout alongside JSON, but it prints JSON at the end.
        # Find the JSON array block.
        out = result.stdout
        # Extract the last valid array JSON
        start_idx = out.rfind("[")
        if start_idx == -1:
            raise Exception("Walrus CLI output JSON not found")
        
        json_data = json.loads(out[start_idx:])
        
        if len(json_data) > 0:
            blob_info = json_data[0]
            if "blobStoreResult" in blob_info:
                blob_info = blob_info["blobStoreResult"]
                
            if "newlyCreated" in blob_info:
                return blob_info["newlyCreated"]["blobObject"]["blobId"]
            elif "alreadyCertified" in blob_info:
                return blob_info["alreadyCertified"]["blobId"]
                
        raise Exception(f"Unexpected response from Walrus CLI: {json_data}")

    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

@with_retries(max_retries=3, initial_backoff=1)
def read_blob(blob_id: str) -> bytes:
    """
    Retrieves a blob's raw bytes from Walrus using the local CLI.
    """
    tmp_path = os.path.join(tempfile.gettempdir(), f"walrus_download_{uuid.uuid4().hex}")
    try:
        cmd = ["walrus", "read", blob_id, "--out", tmp_path]
        subprocess.run(cmd, check=True, capture_output=True)
        
        if not os.path.exists(tmp_path):
            raise Exception("Walrus CLI failed to write the blob file")
            
        with open(tmp_path, "rb") as f:
            return f.read()
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
