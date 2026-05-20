"""
main.py — Tenthline FastAPI application entry point.

Serves:
  - /api/*        → document processing API
  - /             → frontend static files (index.html, style.css, app.js)
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.routers.process import router as process_router

# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Tenthline",
    description="Court-ready document line numbering — PDF & DOCX",
    version="1.0.0",
)

# CORS — allow all origins in dev; tighten for production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API routes ─────────────────────────────────────────────────────────────────
app.include_router(process_router)

# ── Health check ───────────────────────────────────────────────────────────────
@app.get("/api/health", tags=["meta"])
async def health():
    return {"status": "ok", "service": "tenthline"}

# ── Static frontend ────────────────────────────────────────────────────────────
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")

