"""
pdf_processor.py — Annotates a PDF with court-style tenth-line numbers.

For each page (after skip_pages), it:
  1. Detects visual lines via line_counter.extract_visual_lines()
  2. Stamps a line number in the left gutter at every `interval`-th line
  3. Optionally draws a faint vertical rule in the gutter
  4. Returns the modified PDF as bytes
"""

from pathlib import Path
import fitz  # PyMuPDF
from typing import Optional
from backend.utils.line_counter import extract_visual_lines

# ── Appearance constants ───────────────────────────────────────────────────────
GUTTER_X_LEFT   = 28.0   # Default X position (will be adjusted by auto-margin)
RULE_LINE_X     = 36.0   # X position of faint vertical rule (left-margin mode)
NUMBER_FONTSIZE = 12.0
NUMBER_COLOR    = (0.0, 0.0, 0.0)      # Pure black for better legibility at 12pt
RULE_COLOR      = (0.75, 0.75, 0.75)   # light grey
RULE_WIDTH      = 0.4
TOP_MARGIN_SKIP    = 72.0              # Skip text above 1 inch (headers)
BOTTOM_MARGIN_SKIP = 72.0              # Skip text below 1 inch (footers)

# Font path for Bookman Old Style (Bold/Demi)
BOOKMAN_BOLD_PATH = "/usr/share/fonts/opentype/urw-base35/URWBookman-Demi.otf"


def _draw_gutter_rule(page: fitz.Page, margin_side: str) -> None:
    """Draw a faint vertical line in the gutter to guide the eye."""
    pw = page.rect.width
    ph = page.rect.height
    if margin_side == "left":
        x = RULE_LINE_X
    else:
        x = pw - RULE_LINE_X
    shape = page.new_shape()
    shape.draw_line(fitz.Point(x, 36), fitz.Point(x, ph - 36))
    shape.finish(color=RULE_COLOR, width=RULE_WIDTH)
    shape.commit()


def _stamp_number(
    page: fitz.Page,
    number: int,
    y_origin: float,
    margin_side: str,
    page_min_x: float = GUTTER_X_LEFT,
) -> None:
    """Write a right-aligned line number in the gutter at the given Y baseline."""
    label = f"-{number}"
    pw = page.rect.width

    # Use the detected page margin to avoid overlap. 
    # Position the number 12 points to the left of the leftmost text.
    safe_gutter_x = min(GUTTER_X_LEFT, page_min_x - 12.0)

    # Use a fallback font name if Bookman isn't properly registered
    font_name = "bookman-bold"
    
    try:
        text_width = fitz.get_text_length(label, fontsize=NUMBER_FONTSIZE, fontname=font_name)
    except ValueError:
        # Fallback to 'helv' for length calculation if 'bookman-bold' is not recognized globally by fitz
        text_width = fitz.get_text_length(label, fontsize=NUMBER_FONTSIZE, fontname="helv")

    if margin_side == "left":
        # Right-align to safe_gutter_x
        x = safe_gutter_x - text_width
    else:
        # For right margin, we align relative to the right edge
        x = pw - safe_gutter_x + 4

    # Clamp so it never goes off-page
    x = max(x, 4.0)

    point = fitz.Point(x, y_origin)
    page.insert_text(
        point,
        label,
        fontsize=NUMBER_FONTSIZE,
        color=NUMBER_COLOR,
        fontname=font_name,
    )


def annotate_pdf(
    pdf_bytes: bytes,
    interval: int = 10,
    skip_pages: int = 1,
    margin_side: str = "left",
    draw_rule: bool = True,
) -> bytes:
    """
    Main entry point.

    Args:
        pdf_bytes:   Raw PDF file content.
        interval:    Stamp a number every N visual lines (default 10).
        skip_pages:  Number of pages to skip from the front (default 1 = cover).
        margin_side: "left" or "right".
        draw_rule:   Whether to draw the faint vertical gutter rule.

    Returns:
        Modified PDF as bytes.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    total_pages = len(doc)

    for page_idx in range(total_pages):
        page = doc[page_idx]

        if page_idx < skip_pages:
            continue  # Leave cover / title pages untouched

        visual_lines = extract_visual_lines(page, page_idx)

        # Content Zone Filter: Skip headers and footers
        page_height = page.rect.height
        body_lines = [
            vl for vl in visual_lines 
            if TOP_MARGIN_SKIP < vl.y_origin < (page_height - BOTTOM_MARGIN_SKIP)
        ]

        # SILENT IGNORE: If the page has fewer than 10 body lines, skip entirely
        if len(body_lines) < 10:
            continue

        # Auto-Margin Detection: Find the leftmost text boundary on this page
        # This ensures our larger 12pt font doesn't overlap with wide text.
        page_min_x = min(vl.x_start for vl in body_lines) if body_lines else GUTTER_X_LEFT

        # Register Bookman font for this page
        if Path(BOOKMAN_BOLD_PATH).exists():
            # Use a standard name that fitz can potentially recognize globally after registration
            page.insert_font(fontfile=BOOKMAN_BOLD_PATH, fontname="bookman-bold")
        else:
            # Fallback to Times-Bold if Bookman is missing
            page.insert_font(fontname="bookman-bold", fontname_res="ti-bo")

        if draw_rule:
            _draw_gutter_rule(page, margin_side)

        for idx, vl in enumerate(body_lines, 1):
            if idx % interval == 0:
                _stamp_number(page, idx, vl.y_origin, margin_side, page_min_x=page_min_x)

    output = doc.tobytes(garbage=4, deflate=True)
    doc.close()
    return output
