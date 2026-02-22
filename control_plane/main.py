from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from control_plane.upload import router as upload_router
from control_plane.db import init_db
from fastapi.staticfiles import StaticFiles
import os

print("MAIN FILE LOADED")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# init DB
init_db()

# include upload routes
app.include_router(upload_router)

@app.get("/")
def root():
    return {"message": "Control plane running"}

# serve demo player
app.mount("/demo", StaticFiles(directory="demo", html=True), name="demo")

# serve HLS
os.makedirs("storage/hls", exist_ok=True)
app.mount("/hls", StaticFiles(directory="storage/hls"), name="hls")