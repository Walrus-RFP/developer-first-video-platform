import collections
import os
import threading
from utils.walrus import read_blob
from utils.logger import logger

CACHE_DIR = os.path.join("storage", "cache")
os.makedirs(CACHE_DIR, exist_ok=True)


class ChunkCache:
    def __init__(
        self,
        max_ram_size: int = 500 * 1024 * 1024,   # 500 MB
        max_disk_size: int = 2 * 1024 * 1024 * 1024,  # 2 GB
    ):
        self.max_ram_size = max_ram_size
        self.max_disk_size = max_disk_size
        self.current_ram_size = 0
        self.ram_cache: collections.OrderedDict = collections.OrderedDict()
        self._lock = threading.Lock()

    def get_chunk(self, blob_id: str) -> bytes:
        # 1. Memory hit (lock for OrderedDict mutation)
        with self._lock:
            if blob_id in self.ram_cache:
                self.ram_cache.move_to_end(blob_id)
                logger.debug("Cache HIT (RAM)", extra={"blob_id": blob_id})
                return self.ram_cache[blob_id]

        # 2. Disk hit (no lock needed for read; lock only for RAM insertion)
        disk_path = os.path.join(CACHE_DIR, blob_id)
        if os.path.exists(disk_path):
            logger.debug("Cache HIT (disk)", extra={"blob_id": blob_id})
            try:
                os.utime(disk_path, None)
            except OSError:
                pass

            with open(disk_path, "rb") as f:
                data = f.read()
            self._add_to_ram(blob_id, data)
            return data

        # 3. Walrus fetch (slow path)
        logger.info("Cache MISS — fetching from Walrus", extra={"blob_id": blob_id})
        data = read_blob(blob_id)

        if not data:
            raise Exception(f"Failed to read blob {blob_id} from Walrus")

        self._add_to_disk(blob_id, data)
        self._add_to_ram(blob_id, data)
        return data

    def _add_to_ram(self, blob_id: str, data: bytes):
        data_len = len(data)
        with self._lock:
            # Evict oldest entries until there's room
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

        # Collect current disk usage
        files = []
        total_size = 0
        try:
            for fname in os.listdir(CACHE_DIR):
                f_path = os.path.join(CACHE_DIR, fname)
                if os.path.isfile(f_path):
                    try:
                        f_size = os.path.getsize(f_path)
                        f_atime = os.path.getatime(f_path)
                        files.append({"path": f_path, "size": f_size, "atime": f_atime})
                        total_size += f_size
                    except OSError:
                        pass
        except OSError:
            pass

        # Evict oldest by access time until there is room
        if total_size + data_len > self.max_disk_size:
            files.sort(key=lambda x: x["atime"])
            evicted = 0
            while total_size + data_len > self.max_disk_size and files:
                oldest = files.pop(0)
                try:
                    os.unlink(oldest["path"])
                    total_size -= oldest["size"]
                    evicted += 1
                except OSError:
                    pass
            if evicted:
                logger.info("Disk cache LRU eviction", extra={"evicted_count": evicted})

        try:
            with open(disk_path, "wb") as f:
                f.write(data)
            logger.debug("Cache saved (disk)", extra={"blob_id": blob_id})
        except OSError as e:
            logger.warning("Failed to write disk cache: %s", e, extra={"blob_id": blob_id})


# Global singleton for the data plane process
chunk_cache = ChunkCache()
