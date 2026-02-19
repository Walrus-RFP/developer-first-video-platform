import os
import json

STORAGE_DIR = "storage"


def merge_chunks(session_id: str, output_filename="final_video.bin"):
    session_dir = os.path.join(STORAGE_DIR, session_id)
    manifest_path = os.path.join(session_dir, "manifest.json")

    if not os.path.exists(manifest_path):
        raise Exception("Manifest not found")

    with open(manifest_path, "r") as f:
        manifest = json.load(f)

    chunks = manifest["chunks"]

    # sort by chunk_index
    chunks = sorted(chunks, key=lambda x: x["chunk_index"])

    output_path = os.path.join(session_dir, output_filename)

    with open(output_path, "wb") as outfile:
        for chunk in chunks:
            chunk_file = os.path.join(session_dir, chunk["chunk_id"])

            if not os.path.exists(chunk_file):
                raise Exception(f"Missing chunk {chunk['chunk_id']}")

            with open(chunk_file, "rb") as infile:
                outfile.write(infile.read())

    return output_path
