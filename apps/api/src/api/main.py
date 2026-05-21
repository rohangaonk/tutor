from fastapi import FastAPI

app = FastAPI(title="Tutor API")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
