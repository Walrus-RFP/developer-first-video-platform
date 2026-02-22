import collections
import os
import shutil
from utils.walrus import read_blob

CACHE_DIR = os.path.join("storage", "cache")
os.makedirs(CACHE_DIR, exist_ok=True)

class ChunkCache:
    def __init__(self, max_ram_size=500 * 1024 * 1024, max_disk_size=2 * 1024 * 1024 * 1024):
        self.max_ram_size = max_ram_size
        self.max_disk_size = max_disk_size
        self.current_ram_size = 0
        self.ram_cache = collections.OrderedDict()

    def get_chunk(self, blob_id: str) -> bytes:
        # 1. Memory Check
        if blob_id in self.ram_cache:
            self.ram_cache.move_to_end(blob_id)
            print(f"[CACHE HIT - RAM] {blob_id}")
            return self.ram_cache[blob_id]
        
        # 2. Disk Check
        disk_path = os.path.join(CACHE_DIR, blob_id)
        if os.path.exists(disk_path):
            print(f"[CACHE HIT - DISK] {blob_id}")
            with open(disk_path, "rb") as f:
                data = f.read()
            self._add_to_ram(blob_id, data)
            return data
            
        # 3. Walrus Fetch
        print(f"[CACHE MISS] Fetching {blob_id} from Walrus...")
        data = read_blob(blob_id)
        
        if not data:
            raise Exception(f"Failed to read blob {blob_id} from Walrus")
            
        self._add_to_disk(blob_id, data)
        self._add_to_ram(blob_id, data)
        return data

    def _add_to_ram(self, blob_id: str, data: bytes):
        data_len = len(data)
        while self.current_ram_size + data_len > self.max_ram_size and self.ram_cache:
            old_id, old_data = self.ram_cache.popitem(last=False)
            self.current_ram_size -= len(old_data)
            print(f"[CACHE EVICT - RAM] {old_id}")
            
        self.ram_cache[blob_id] = data
        self.current_ram_size += data_len
        self.ram_cache.move_to_end(blob_id)

    def _add_to_disk(self, blob_id: str, data: bytes):
        # Very simple disk limit check (just count files or total dir size)
        # For speed, we'll just check if the directory is roughly over limit
        # In a real system we'd use a more precise LRU for disk too
        disk_path = os.path.join(CACHE_DIR, blob_id)
        
        # If disk is getting full, just clear it (simplest way for now)
        # This is better than out of disk space errors
        # Note: In production we would do something more surgical
        # But for this RFP, clearing cache if over 2GB is reasonable
        total_size = sum(os.path.getsize(os.path.join(CACHE_DIR, f)) for f in os.listdir(CACHE_DIR) if os.path.isfile(os.path.join(CACHE_DIR, f)))
        if total_size + len(data) > self.max_disk_size:
            print("[CACHE CLEANUP - DISK] Clearing disk cache to free space")
            for f in os.listdir(CACHE_DIR):
                file_p = os.path.join(CACHE_DIR, f)
                try:
                    if os.path.isfile(file_p): os.unlink(file_p)
                except: pass

        with open(disk_path, "wb") as f:
            f.write(data)
        print(f"[CACHE SAVED - DISK] {blob_id}")

# Global singleton cache for the data plane
chunk_cache = ChunkCache()
