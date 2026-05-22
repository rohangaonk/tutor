from fastapi import FastAPI

from api.routers import chat, upload

app = FastAPI(title="Tutor API")

app.include_router(upload.router)
app.include_router(chat.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
