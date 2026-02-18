from fastapi import APIRouter, UploadFile, File
import os

router = APIRouter()

STORAGE_DIR = "storage"

os.makedirs(STORAGE_DIR, exist_ok=True)

@router.post("/upload-chunk/{session_id}/{chunk_id}")
async def upload_chunk(session_id: str, chunk_id: str, file: UploadFile = File(...)):
    session_dir = os.path.join(STORAGE_DIR, session_id)
    os.makedirs(session_dir, exist_ok=True)

    file_path = os.path.join(session_dir, chunk_id)

    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)

    return {"status": "chunk stored"}
