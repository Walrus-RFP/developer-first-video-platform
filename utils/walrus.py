import os
import json
import time
from utils.logger import logger
import functools
import urllib.request
import urllib.error

# Accept both naming conventions: docker-compose uses WALRUS_* while legacy code used *_URL
PUBLISHER_URL = (
    os.environ.get("WALRUS_PUBLISHER")
    or os.environ.get("PUBLISHER_URL")
    or "https://publisher.walrus-testnet.walrus.space"
)
AGGREGATOR_URL = (
    os.environ.get("WALRUS_AGGREGATOR")
    or os.environ.get("AGGREGATOR_URL")
    or "https://aggregator.walrus-testnet.walrus.space"
)

REQUEST_TIMEOUT = int(os.environ.get("WALRUS_TIMEOUT", "30"))


def with_retries(max_retries=3, initial_backoff=1, max_backoff=30):
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
                        logger.error("Final failure after %d attempts: %s", max_retries, e)
                        raise
                    logger.warning("Attempt %d failed: %s. Retrying in %ds...", retries, e, backoff)
                    time.sleep(backoff)
                    backoff = min(backoff * 2, max_backoff)
        return wrapper
    return decorator


@with_retries(max_retries=5, initial_backoff=2)
def store_blob(data: bytes, epochs: int = 5) -> str:
    """
    Stores a blob in Walrus using HTTP endpoints.
    Returns the blob_id as a string.
    """
    url = f"{PUBLISHER_URL}/v1/blobs?epochs={epochs}"
    req = urllib.request.Request(url, data=data, method="PUT")
    req.add_header("User-Agent", "WalrusVideoSDK/1.0")

    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
            out = response.read().decode("utf-8")
            json_data = json.loads(out)

            if "newlyCreated" in json_data:
                return json_data["newlyCreated"]["blobObject"]["blobId"]

            elif "alreadyCertified" in json_data:
                blob_id = json_data["alreadyCertified"]["blobId"]

                # Verify the aggregator actually has it (publisher cache can be stale)
                check_url = f"{AGGREGATOR_URL}/v1/blobs/{blob_id}"
                check_req = urllib.request.Request(check_url, method="GET")
                try:
                    with urllib.request.urlopen(check_req, timeout=REQUEST_TIMEOUT) as check_resp:
                        check_resp.read(1)
                    return blob_id
                except urllib.error.HTTPError as he:
                    if he.code == 404:
                        # Blob was pruned on testnet — raise so the retry decorator
                        # retries with the same data (publisher will assign a new slot).
                        raise Exception(
                            f"Publisher returned alreadyCertified but aggregator returned 404 "
                            f"for blob {blob_id}. Blob likely pruned; will retry."
                        )
                    raise he

            raise Exception(f"Unexpected Walrus Publisher response: {json_data}")

    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        raise Exception(f"HTTPError {e.code}: {err_body}")


def read_blob(blob_id: str) -> bytes:
    """
    Retrieves a blob's raw bytes from Walrus.
    Fast-fails on 404 (blob permanently missing) — does NOT retry.
    Retries up to 30 times on transient network errors (useful for
    testnet propagation delays right after upload).
    """
    url = f"{AGGREGATOR_URL}/v1/blobs/{blob_id}"
    req = urllib.request.Request(url, method="GET")
    req.add_header("User-Agent", "WalrusVideoSDK/1.0")

    max_retries = 30
    initial_backoff = 2
    max_backoff = 10
    backoff = initial_backoff

    for attempt in range(1, max_retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
                return response.read()
        except urllib.error.HTTPError as e:
            if e.code in (400, 404):
                # Permanent errors — no point retrying
                err_body = e.read().decode("utf-8")
                raise Exception(f"HTTPError {e.code}: {err_body}")
            err_body = e.read().decode("utf-8")
            last_error = Exception(f"HTTPError {e.code}: {err_body}")
        except Exception as e:
            last_error = e

        if attempt >= max_retries:
            logger.error("Final failure reading blob %s after %d attempts", blob_id, max_retries)
            raise last_error

        logger.warning(
            "Attempt %d/%d failed reading blob %s: %s. Retrying in %ds...",
            attempt, max_retries, blob_id, last_error, backoff
        )
        time.sleep(backoff)
        backoff = min(backoff * 2, max_backoff)
