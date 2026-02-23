import collections
import os
import shutil
from utils.walrus import read_blob
from utils.logger import logger

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
            logger.debug("Cache HIT (RAM)", extra={"blob_id": blob_id})
            return self.ram_cache[blob_id]
        
        # 2. Disk Check
        disk_path = os.path.join(CACHE_DIR, blob_id)
        if os.path.exists(disk_path):
            logger.debug("Cache HIT (disk)", extra={"blob_id": blob_id})
            # Update access time for LRU
            try:
                os.utime(disk_path, None) 
            except OSError:
                pass
                
            with open(disk_path, "rb") as f:
                data = f.read()
            self._add_to_ram(blob_id, data)
            return data
            
        # 3. Walrus Fetch
        logger.info("Cache MISS — fetching from Walrus", extra={"blob_id": blob_id})
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
            logger.debug("Cache evict (RAM)", extra={"blob_id": old_id})
            
        self.ram_cache[blob_id] = data
        self.current_ram_size += data_len
        self.ram_cache.move_to_end(blob_id)

    def _add_to_disk(self, blob_id: str, data: bytes):
        disk_path = os.path.join(CACHE_DIR, blob_id)
        data_len = len(data)

        # 1. Calculate current size
        files = []
        total_size = 0
        for f in os.listdir(CACHE_DIR):
            f_path = os.path.join(CACHE_DIR, f)
            if os.path.isfile(f_path):
                f_size = os.path.getsize(f_path)
                # Store path, size, and last access/modified time
                files.append({
                    "path": f_path,
                    "size": f_size,
                    "atime": os.path.getatime(f_path)
                })
                total_size += f_size

        # 2. Evict until we have enough space
        if total_size + data_len > self.max_disk_size:
            # Sort by access time (oldest first)
            files.sort(key=lambda x: x["atime"])
            
            evicted_count = 0
            while total_size + data_len > self.max_disk_size and files:
                oldest = files.pop(0)
                try:
                    os.unlink(oldest["path"])
                    total_size -= oldest["size"]
                    evicted_count += 1
                except OSError:
                    pass
            
            if evicted_count > 0:
                logger.info("Disk cache LRU eviction triggered", extra={"evicted_count": evicted_count})

        with open(disk_path, "wb") as f:
            f.write(data)
        logger.debug("Cache saved (disk)", extra={"blob_id": blob_id})

# Global singleton cache for the data plane
chunk_cache = ChunkCache()
