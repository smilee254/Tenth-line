"""
docx_processor.py — Converts a .docx file to PDF then hands off to pdf_processor.

Pipeline:
  .docx bytes  →  temp file  →  LibreOffice headless  →  PDF bytes  →  pdf_processor

LibreOffice is the most faithful renderer for .docx (preserves fonts, spacing,
tables, headers/footers) and is available on Linux/macOS/Windows.
Falls back gracefully with an informative error if LibreOffice is not installed.
"""

import io
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from backend.processors.pdf_processor import annotate_pdf


SOFFICE_CANDIDATES = [
    "soffice",
    "libreoffice",
    "/usr/bin/soffice",
    "/usr/lib/libreoffice/program/soffice",
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
]


def _find_soffice() -> Optional[str]:
    for candidate in SOFFICE_CANDIDATES:
        path = shutil.which(candidate) or (candidate if Path(candidate).exists() else None)
        if path:
            return path
    return None


def convert_docx_to_pdf_bytes(docx_bytes: bytes) -> bytes:
    """Convert raw .docx bytes → raw PDF bytes via LibreOffice headless."""
    soffice = _find_soffice()
    if soffice is None:
        raise RuntimeError(
            "LibreOffice is not installed or not in PATH. "
            "Install it with: sudo apt install libreoffice  (Ubuntu/Debian) "
            "or brew install --cask libreoffice  (macOS)."
        )

    with tempfile.TemporaryDirectory() as tmpdir:
        docx_path = Path(tmpdir) / "input.docx"
        pdf_path  = Path(tmpdir) / "input.pdf"

        docx_path.write_bytes(docx_bytes)

        result = subprocess.run(
            [
                soffice,
                "--headless",
                "--convert-to", "pdf",
                "--outdir", tmpdir,
                str(docx_path),
            ],
            capture_output=True,
            timeout=120,
        )

        if result.returncode != 0:
            stderr = result.stderr.decode(errors="replace")
            raise RuntimeError(f"LibreOffice conversion failed:\n{stderr}")

        if not pdf_path.exists():
            raise RuntimeError("LibreOffice did not produce an output PDF.")

        return pdf_path.read_bytes()


def process_docx(
    docx_bytes: bytes,
    interval: int = 10,
    skip_pages: int = 1,
    margin_side: str = "left",
    draw_rule: bool = True,
) -> bytes:
    """Full pipeline: .docx bytes → annotated PDF bytes."""
    pdf_bytes = convert_docx_to_pdf_bytes(docx_bytes)
    return annotate_pdf(
        pdf_bytes,
        interval=interval,
        skip_pages=skip_pages,
        margin_side=margin_side,
        draw_rule=draw_rule,
    )

