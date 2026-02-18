from fastapi import FastAPI
from control_plane.upload import router as upload_router

app = FastAPI()
app.include_router(upload_router)

@app.get("/")
def root():
    return {"message": "Control plane running"}
