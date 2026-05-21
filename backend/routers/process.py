"""
routers/process.py — /api/process endpoint.
Accepts a file upload + JSON options, returns an annotated PDF.
"""

import io
import os
import shutil
import tempfile
from typing import Literal, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool

from backend.processors.pdf_processor import annotate_pdf
from backend.processors.docx_processor import process_docx

router = APIRouter(prefix="/api", tags=["process"])

ALLOWED_TYPES = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    # Some browsers send these
    "application/octet-stream": None,   # Determined by extension
}


def _detect_file_type(filename: str, content_type: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext == "pdf":
        return "pdf"
    if ext == "docx":
        return "docx"
    # Fall back to MIME
    if content_type in ALLOWED_TYPES and ALLOWED_TYPES[content_type]:
        return ALLOWED_TYPES[content_type]
    raise HTTPException(
        status_code=422,
        detail=f"Unsupported file type '{ext}'. Please upload a .pdf or .docx file.",
    )


def _cleanup_files(*paths: str):
    """Background task to remove temporary files after response is sent."""
    for path in paths:
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass


@router.post("/process")
async def process_document(
    file: UploadFile = File(...),
    interval: int = Form(10),
    skip_pages: int = Form(1),
    margin_side: str = Form("left"),
    draw_rule: bool = Form(True),
):
    """
    Process a PDF or DOCX file and return an annotated PDF with court-style
    tenth-line numbers in the margin.
    """
    if not file.filename:
        raise HTTPException(status_code=422, detail="Uploaded file has no filename.")

    file_type = _detect_file_type(file.filename or "", file.content_type or "")

    # Validate options
    if interval < 1 or interval > 100:
        raise HTTPException(status_code=422, detail="interval must be between 1 and 100.")
    if skip_pages < 0 or skip_pages > 50:
        raise HTTPException(status_code=422, detail="skip_pages must be between 0 and 50.")
    if margin_side not in ("left", "right"):
        raise HTTPException(status_code=422, detail="margin_side must be 'left' or 'right'.")

    # 1. Stream the uploaded file to a temporary file on disk (Saves RAM)
    fd_in, temp_in = tempfile.mkstemp(suffix=f".{file_type}")
    with os.fdopen(fd_in, "wb") as f_in:
        shutil.copyfileobj(file.file, f_in)

    fd_out, temp_out = tempfile.mkstemp(suffix=".pdf")
    os.close(fd_out) # We only need the path, processor will overwrite

    try:
        # 2. Process off the main thread (Prevents freezing the server)
        if file_type == "pdf":
            await run_in_threadpool(
                annotate_pdf,
                temp_in,
                temp_out,
                interval=interval,
                skip_pages=skip_pages,
                margin_side=margin_side,
                draw_rule=draw_rule,
            )
        else:
            await run_in_threadpool(
                process_docx,
                temp_in,
                temp_out,
                interval=interval,
                skip_pages=skip_pages,
                margin_side=margin_side,
                draw_rule=draw_rule,
            )
    except Exception as e:
        _cleanup_files(temp_in, temp_out)
        raise HTTPException(status_code=500, detail=str(e))

    stem = (file.filename or "document").rsplit(".", 1)[0]
    download_name = f"{stem}_tenthlined.pdf"

    # 3. Stream the file back from disk, clean up temps when done (Saves RAM)
    return FileResponse(
        temp_out,
        media_type="application/pdf",
        filename=download_name,
        headers={"X-Filename": download_name},
        background=BackgroundTask(_cleanup_files, temp_in, temp_out),
    )
