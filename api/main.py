from __future__ import annotations

from fastapi import FastAPI

from api.chat_routes import router as chat_router
from config.settings import get_settings
from db.connection import ensure_database_ready


app = FastAPI(title="DMRB API")
app.include_router(chat_router)


@app.get("/health")
def health():
    return {"ok": True}


@app.on_event("startup")
def startup():
    ensure_database_ready(get_settings().database_path)
