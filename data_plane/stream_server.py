from fastapi import FastAPI
from data_plane.chunk_upload import router as chunk_router

app = FastAPI()
app.include_router(chunk_router)

@app.get("/")
def root():
    return {"message": "Data plane running"}
