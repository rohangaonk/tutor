from fastapi import FastAPI

from api.routers import upload

app = FastAPI(title="Tutor API")

app.include_router(upload.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
