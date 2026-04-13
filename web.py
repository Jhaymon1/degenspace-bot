import os
from fastapi import FastAPI

app = FastAPI()


@app.get("/")
def root():
    return {"ok": True, "service": "degenspace-bot"}


@app.get("/healthz")
def healthz():
    return {"ok": True}


def port() -> int:
    raw = os.getenv("PORT", "10000")
    try:
        return int(raw)
    except ValueError:
        raise ValueError(f"Invalid PORT value: {raw!r}. PORT must be a numeric string.")
