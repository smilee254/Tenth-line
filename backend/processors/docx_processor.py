"""
docx_processor.py — Converts a .docx file to PDF then hands off to pdf_processor.

Pipeline:
  .docx bytes
    → font pre-processing  (replace Windows font names with installed Linux equivalents)
    → LibreOffice headless  (no font substitution needed — finds fonts natively)
    → PDF bytes
    → pdf_processor         (smart counting, right-margin stamping, gutter rule)

Font pre-processing is the key fix for text distortion:
  LibreOffice performs its own (imprecise) font substitution when it encounters
  Windows-only fonts.  By replacing "Bookman Old Style" → "URW Bookman" at the
  XML level BEFORE handing the file to LibreOffice, we ensure LibreOffice finds
  the exact installed font with identical glyph metrics, preventing any line
  reflow between the original Word document and the converted PDF.
"""

import io
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

from backend.processors.pdf_processor import annotate_pdf


# ── Font substitution map ──────────────────────────────────────────────────────
# Maps Windows/Microsoft font names → metrically-compatible Linux fonts that are
# installed on this server.  These substitutes have identical character widths,
# so line breaking is preserved exactly.
#
# Server fonts confirmed via `fc-match`:
#   "Bookman Old Style"  → URWBookman-Light.otf  (family: "URW Bookman")
#   "Times New Roman"    → Tinos-Regular.ttf       (metrically identical)
#   "Arial"              → Arimo-Regular.ttf        (metrically identical)
#   "Calibri"            → Carlito-Regular.ttf      (metrically identical)
FONT_SUBSTITUTIONS = {
    "Bookman Old Style": "URW Bookman",
    # Uncomment below if documents also use these:
    # "Times New Roman": "Tinos",
    # "Arial": "Arimo",
    # "Calibri": "Carlito",
}

# XML files inside a .docx that may contain font references
_XML_EXTENSIONS = {".xml", ".rels"}


def _preprocess_docx_fonts(docx_bytes: bytes) -> bytes:
    """
    Replace Windows-specific font names in a DOCX with their installed
    Linux equivalents directly in the ZIP XML, so LibreOffice finds the
    font natively without falling back to its own imprecise substitution.
    """
    buf_in  = io.BytesIO(docx_bytes)
    buf_out = io.BytesIO()

    with zipfile.ZipFile(buf_in, "r") as zin, \
         zipfile.ZipFile(buf_out, "w", compression=zipfile.ZIP_DEFLATED) as zout:

        for item in zin.infolist():
            data = zin.read(item.filename)
            suffix = Path(item.filename).suffix.lower()

            if suffix in _XML_EXTENSIONS:
                try:
                    text = data.decode("utf-8")
                    for win_font, linux_font in FONT_SUBSTITUTIONS.items():
                        text = text.replace(win_font, linux_font)
                    data = text.encode("utf-8")
                except (UnicodeDecodeError, Exception):
                    pass  # Leave unparseable entries as-is

            zout.writestr(item, data)

    return buf_out.getvalue()


# ── LibreOffice helpers ────────────────────────────────────────────────────────

SOFFICE_CANDIDATES = [
    "soffice",
    "libreoffice",
    "/usr/bin/soffice",
    "/usr/lib/libreoffice/program/soffice",
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
]


def _find_soffice() -> Optional[str]:
    for candidate in SOFFICE_CANDIDATES:
        path = shutil.which(candidate) or (
            candidate if Path(candidate).exists() else None
        )
        if path:
            return path
    return None


def convert_docx_to_pdf_bytes(docx_bytes: bytes) -> bytes:
    """
    Convert raw .docx bytes → raw PDF bytes via LibreOffice headless.

    Font pre-processing is applied first to prevent text reflow.
    """
    soffice = _find_soffice()
    if soffice is None:
        raise RuntimeError(
            "LibreOffice is not installed or not in PATH. "
            "Install with: sudo apt install libreoffice"
        )

    # Pre-process fonts BEFORE handing to LibreOffice
    processed_docx = _preprocess_docx_fonts(docx_bytes)

    with tempfile.TemporaryDirectory() as tmpdir:
        docx_path = Path(tmpdir) / "input.docx"
        pdf_path  = Path(tmpdir) / "input.pdf"

        docx_path.write_bytes(processed_docx)

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
    """Full pipeline: .docx bytes → annotated PDF bytes (with all features)."""
    pdf_bytes = convert_docx_to_pdf_bytes(docx_bytes)
    return annotate_pdf(
        pdf_bytes,
        interval=interval,
        skip_pages=skip_pages,
        margin_side=margin_side,
        draw_rule=draw_rule,
    )
