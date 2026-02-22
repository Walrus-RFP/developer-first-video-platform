import os
import tempfile
import json
import uuid
import time
import functools
import urllib.request
import urllib.error

PUBLISHER_URL = os.environ.get("PUBLISHER_URL", "https://publisher.walrus-testnet.walrus.space")
AGGREGATOR_URL = os.environ.get("AGGREGATOR_URL", "https://aggregator.walrus-testnet.walrus.space")

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
    Stores a blob in Walrus using HTTP endpoints (standard lib).
    Returns the newly created blob_id as a string.
    """
    url = f"{PUBLISHER_URL}/v1/blobs?epochs={epochs}"
    req = urllib.request.Request(url, data=data, method="PUT")
    req.add_header("User-Agent", "WalrusVideoSDK/1.0")
    
    try:
        with urllib.request.urlopen(req) as response:
            out = response.read().decode('utf-8')
            json_data = json.loads(out)
            
            if "newlyCreated" in json_data:
                return json_data["newlyCreated"]["blobObject"]["blobId"]
            elif "alreadyCertified" in json_data:
                return json_data["alreadyCertified"]["blobId"]
                
            raise Exception(f"Unexpected Walrus Publisher response: {json_data}")
    except urllib.error.HTTPError as e:
        err_body = e.read().decode('utf-8')
        raise Exception(f"HTTPError {e.code}: {err_body}")

@with_retries(max_retries=3, initial_backoff=1)
def read_blob(blob_id: str) -> bytes:
    """
    Retrieves a blob's raw bytes from Walrus using HTTP endpoints.
    """
    url = f"{AGGREGATOR_URL}/v1/blobs/{blob_id}"
    req = urllib.request.Request(url, method="GET")
    req.add_header("User-Agent", "WalrusVideoSDK/1.0")
    
    try:
        with urllib.request.urlopen(req) as response:
            return response.read()
    except urllib.error.HTTPError as e:
        err_body = e.read().decode('utf-8')
        raise Exception(f"HTTPError {e.code}: {err_body}")
