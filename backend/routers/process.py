"""
routers/process.py — /api/process endpoint.
Accepts a file upload + JSON options, returns an annotated PDF.
"""

import io
from typing import Literal, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

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

    Form fields:
      - file        : The uploaded .pdf or .docx
      - interval    : Number every N-th line (default 10)
      - skip_pages  : Pages to leave unnumbered from the front (default 1)
      - margin_side : "left" or "right" (default "left")
      - draw_rule   : Whether to draw a faint vertical gutter rule (default true)
    """
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=422, detail="Uploaded file is empty.")

    file_type = _detect_file_type(file.filename or "", file.content_type or "")

    # Validate options
    if interval < 1 or interval > 100:
        raise HTTPException(status_code=422, detail="interval must be between 1 and 100.")
    if skip_pages < 0 or skip_pages > 50:
        raise HTTPException(status_code=422, detail="skip_pages must be between 0 and 50.")
    if margin_side not in ("left", "right"):
        raise HTTPException(status_code=422, detail="margin_side must be 'left' or 'right'.")

    try:
        if file_type == "pdf":
            # PDF: stamp gutter numbers directly onto the existing PDF
            result_bytes = annotate_pdf(
                raw,
                interval=interval,
                skip_pages=skip_pages,
                margin_side=margin_side,
                draw_rule=draw_rule,
            )
            stem = (file.filename or "document").rsplit(".", 1)[0]
            download_name = f"{stem}_tenthlined.pdf"
            media_type = "application/pdf"
        else:
            # DOCX: pre-process fonts → LibreOffice → PDF → annotate
            # Font pre-processing replaces "Bookman Old Style" → "URW Bookman"
            # so LibreOffice uses the installed font natively (no reflow).
            result_bytes = process_docx(
                raw,
                interval=interval,
                skip_pages=skip_pages,
                margin_side=margin_side,
                draw_rule=draw_rule,
            )
            stem = (file.filename or "document").rsplit(".", 1)[0]
            download_name = f"{stem}_tenthlined.pdf"
            media_type = "application/pdf"
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    return StreamingResponse(
        io.BytesIO(result_bytes),
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{download_name}"',
            "X-Filename": download_name,
        },
    )
