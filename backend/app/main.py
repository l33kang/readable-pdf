from fastapi import FastAPI
from app.upload import router as upload_router
from app.processing import router as processing_router

app = FastAPI(title="Scan-to-Text API")

app.include_router(upload_router)
app.include_router(processing_router)


@app.get("/api/health")
def health_check():
    return {"status": "healthy"}
