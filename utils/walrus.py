import os
import tempfile
import json
import uuid
import time
import functools
import requests

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
    Stores a blob in Walrus using HTTP endpoints.
    Returns the newly created blob_id as a string.
    """
    response = requests.put(f"{PUBLISHER_URL}/v1/store?epochs={epochs}", data=data)
    response.raise_for_status()
    json_data = response.json()
    
    if "newlyCreated" in json_data:
        return json_data["newlyCreated"]["blobObject"]["blobId"]
    elif "alreadyCertified" in json_data:
        return json_data["alreadyCertified"]["blobId"]
        
    raise Exception(f"Unexpected Walrus Publisher response: {json_data}")

@with_retries(max_retries=3, initial_backoff=1)
def read_blob(blob_id: str) -> bytes:
    """
    Retrieves a blob's raw bytes from Walrus using HTTP endpoints.
    """
    response = requests.get(f"{AGGREGATOR_URL}/v1/{blob_id}")
    response.raise_for_status()
    return response.content
