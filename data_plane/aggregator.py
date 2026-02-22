import os
import json
import concurrent.futures
from data_plane.cache import chunk_cache

STORAGE_DIR = "storage"

def stream_byte_range(video_id: str, start: int, end: int):
    """
    Generator that parses the manifest and yields the requested byte range
    by fetching specific chunks from the cache (and therefore Walrus).
    Implements parallel pre-fetching for multi-chunk requests.
    """
    # In a production stateless setup, we look in the HLS dir for the manifest
    # (which we enriched with hls_assets earlier)
    manifest_path = os.path.join(STORAGE_DIR, "hls", video_id, "manifest.json")
    
    if not os.path.exists(manifest_path):
        # Fallback to older location
        manifest_path = os.path.join(STORAGE_DIR, video_id, "manifest.json")
        if not os.path.exists(manifest_path):
            raise FileNotFoundError(f"Manifest not found for video {video_id}")
        
    with open(manifest_path, "r") as f:
        manifest = json.load(f)
        
    chunks = sorted(manifest["chunks"], key=lambda x: x["chunk_index"])
    
    current_offset = 0
    remaining_bytes = end - start + 1
    
    # 1. Identify which chunks are actually needed
    needed_blobs = []
    chunk_metadata = [] # stores (chunk_start, chunk_size, blob_id)
    
    temp_offset = 0
    for chunk in chunks:
        c_size = chunk["size"]
        c_start = temp_offset
        c_end = temp_offset + c_size - 1
        
        if start <= c_end and temp_offset <= end:
            needed_blobs.append(chunk["blob_id"])
            chunk_metadata.append((c_start, c_size, chunk["blob_id"]))
            
        temp_offset += c_size

    # 2. Pre-fetch all needed chunks in parallel
    # We use a ThreadPoolExecutor to trigger the cache/Walrus fetches
    print(f"[AGGREGATOR] Parallel fetching {len(needed_blobs)} chunks for range {start}-{end}...")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        # Submit all fetches and map blob_id -> future
        blob_to_future = {
            b_id: executor.submit(chunk_cache.get_chunk, b_id)
            for b_id in needed_blobs
        }
        
        # 3. Yield slices in order as they complete
        # We must maintain order, so we loop through the chunk_metadata
        for c_start, c_size, b_id in chunk_metadata:
            future = blob_to_future[b_id]
            chunk_data = future.result()
            
            # Slice the chunk if we only need part of it
            internal_start = max(0, start - c_start)
            amount_needed = min(remaining_bytes, len(chunk_data) - internal_start)
            internal_end = internal_start + amount_needed
            
            yield chunk_data[internal_start:internal_end]
            
            remaining_bytes -= amount_needed
            start += amount_needed
            
            if remaining_bytes <= 0:
                break
