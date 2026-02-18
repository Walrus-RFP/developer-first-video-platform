from fastapi import APIRouter
import uuid

router = APIRouter()

UPLOAD_SESSIONS = {}

@router.post("/upload-session")
def create_upload_session():
    session_id = str(uuid.uuid4())
    UPLOAD_SESSIONS[session_id] = {
        "status": "created",
        "chunks": []
    }
    return {"upload_session_id": session_id}

@router.get("/upload-session/{session_id}")
def get_upload_session(session_id: str):
    return UPLOAD_SESSIONS.get(session_id, {"error": "not found"})

@router.post("/complete-upload/{session_id}")
def complete_upload(session_id: str):
    if session_id in UPLOAD_SESSIONS:
        UPLOAD_SESSIONS[session_id]["status"] = "completed"
        return {"status": "upload completed"}
    return {"error": "session not found"}
