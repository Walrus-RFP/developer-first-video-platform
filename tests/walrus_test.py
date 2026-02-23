import urllib.request
import json
import time

PUBLISHER_URL = "https://publisher.walrus-testnet.walrus.space"
AGGREGATOR_URL = "https://aggregator.walrus-testnet.walrus.space"

def store_blob(data: bytes, epochs: int = 1) -> str:
    url = f"{PUBLISHER_URL}/v1/blobs?epochs={epochs}"
    req = urllib.request.Request(url, data=data, method="PUT")
    with urllib.request.urlopen(req) as response:
        out = response.read().decode('utf-8')
        json_data = json.loads(out)
        if "newlyCreated" in json_data:
            return json_data["newlyCreated"]["blobObject"]["blobId"]
        elif "alreadyCertified" in json_data:
            return json_data["alreadyCertified"]["blobId"]

def test():
    data = b"Hello Walrus test" * 100
    blob_id = store_blob(data)
    print(f"Stored blob: {blob_id}")
    for i in range(10):
        url = f"{AGGREGATOR_URL}/v1/blobs/{blob_id}"
        print(f"Reading from {url}...")
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req) as response:
                print("SUCCESS:", response.read()[:50])
                break
        except Exception as e:
            print("FAILED:", str(e))
            time.sleep(2)

test()
