from fastapi import FastAPI
from control_plane.upload import router as upload_router
from control_plane.db import init_db

init_db()

app = FastAPI()
app.include_router(upload_router)

@app.get("/")
def root():
    return {"message": "Control plane running"}
