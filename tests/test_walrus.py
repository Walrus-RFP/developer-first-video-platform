"""
Walrus storage integration tests.
These hit the real Walrus testnet — requires network access.

Run:  pytest tests/test_walrus.py -v
"""
import pytest
from utils.walrus import store_blob, read_blob


class TestStoreBlob:
    def test_store_small_blob(self):
        data = b"walrus test payload " * 10
        blob_id = store_blob(data, epochs=1)
        assert isinstance(blob_id, str)
        assert len(blob_id) > 10

    def test_store_returns_string_id(self):
        blob_id = store_blob(b"hello walrus", epochs=1)
        assert isinstance(blob_id, str)

    def test_store_binary_data(self):
        data = bytes(range(256)) * 100
        blob_id = store_blob(data, epochs=1)
        assert blob_id


class TestReadBlob:
    def test_roundtrip(self):
        payload = b"roundtrip test " + b"x" * 1000
        blob_id = store_blob(payload, epochs=1)
        # May need to wait for testnet propagation
        result = read_blob(blob_id)
        assert result == payload

    def test_read_nonexistent_blob_raises(self):
        with pytest.raises(Exception, match="HTTPError"):
            read_blob("nonexistent-blob-id-that-does-not-exist-at-all")

    def test_store_and_read_video_data(self):
        # Simulate a 1MB video chunk
        chunk = bytes([i % 256 for i in range(1024 * 1024)])
        blob_id = store_blob(chunk, epochs=1)
        retrieved = read_blob(blob_id)
        assert retrieved == chunk
        assert len(retrieved) == 1024 * 1024
