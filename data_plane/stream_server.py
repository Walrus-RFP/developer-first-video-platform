from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from data_plane.chunk_upload import router as chunk_router
from control_plane.db import get_video
import os

app = FastAPI()

# existing chunk upload routes
app.include_router(chunk_router)


@app.get("/")
def root():
    return {"message": "Data plane running"}


# ---------------------------------------------------
# Playback Endpoint
# ---------------------------------------------------
@app.get("/play/{video_id}")
def play_video(video_id: str):

    video = get_video(video_id)

    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    file_path = video["file_path"]

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File missing")

    # For now we assume mp4
    return FileResponse(file_path, media_type="video/mp4")
