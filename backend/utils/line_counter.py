"""
line_counter.py — Visual line detection using PyMuPDF span bounding boxes.

Strategy:
  1. Extract all text spans from a page via page.get_text("rawdict").
  2. Group spans whose baseline Y values fall within BASELINE_TOLERANCE of each other.
  3. Sort groups top-to-bottom → these are the visual lines.
  4. Optionally exclude spans that fall inside image/table bounding boxes.

Fixes applied:
  - BASELINE_TOLERANCE raised to 4.0pt to absorb OCR baseline jitter that was
    splitting one visual line into multiple fragments (causing irregular counts).
  - _has_visible_ink() strips whitespace AND Unicode replacement characters
    (U+FFFD) so garbled OCR glyphs don't inflate the line count.
  - Group representative Y is the running average of the group, not just the
    first span, preventing cumulative drift from creating phantom extra lines.
"""

import unicodedata
from dataclasses import dataclass, field
from typing import List
import fitz  # PyMuPDF


# Raised from 2.5 → 4.0 pt to handle OCR baseline jitter (characters on the
# same physical line whose extracted Y values can differ by 3-4 pt).
BASELINE_TOLERANCE = 4.0

# Characters that look "visible" but carry no printable meaning.
# U+FFFD = Unicode Replacement Character (corrupt / undecodable OCR glyph)
# \x00  = Null byte     \xa0 = Non-breaking space
_GARBAGE_CHARS = str.maketrans("", "", "\ufffd\x00\xa0")


def _has_visible_ink(text: str) -> bool:
    """
    Return True only if *text* contains meaningful printable content.

    Three-pass strategy:
      1. Strip ordinary whitespace — catches blank / space-only lines.
      2. Remove known garbage Unicode code-points (U+FFFD, null, NBSP).
      3. Unicode-category check — at least one Letter (L*) or Number (N*)
         must be present.  Punctuation-only content is allowed only when
         it contains ≥ 3 non-space characters, so separator lines like
         "___________" or "----------" are still counted, but isolated
         OCR ghost glyphs like · (U+00B7 MIDDLE DOT) that fitz synthesises
         when reading back corrupt PDF glyph encodings are rejected.
    """
    # Pass 1 — whitespace
    stripped = text.strip()
    if not stripped:
        return False
    # Pass 2 — remove known garbage code-points
    meaningful = stripped.translate(_GARBAGE_CHARS).strip()
    if not meaningful:
        return False
    # Pass 3 — Unicode category check
    for ch in meaningful:
        cat = unicodedata.category(ch)
        if cat[0] in ('L', 'N'):   # Letter or Number → definitely real content
            return True
    # No letters or digits: allow only if there are ≥ 3 non-space chars
    # (handles legitimate separator / underline lines in legal documents).
    return sum(1 for c in meaningful if not c.isspace()) >= 3


@dataclass
class VisualLine:
    page_num: int          # 0-indexed
    line_num: int          # 1-indexed, resets per page
    y_baseline: float      # top-of-line Y coordinate
    y_origin: float        # actual text baseline Y coordinate
    y_bottom: float        # bottom of the tallest span
    x_start: float         # leftmost X of text on this line
    x_end: float           # rightmost X of text on this line
    spans: list = field(default_factory=list)  # raw span dicts


def _get_exclusion_rects(page: fitz.Page) -> List[fitz.Rect]:
    """Return bounding boxes for images and table-like drawings to skip."""
    exclusions: List[fitz.Rect] = []

    # Images
    for img in page.get_images(full=True):
        for item in page.get_image_rects(img[0]):
            exclusions.append(item)

    # Large filled rectangles (table borders / shading)
    for path in page.get_drawings():
        rect = fitz.Rect(path["rect"])
        # Only flag rects wider than 30% of page and taller than 1 line (~12pt)
        if rect.width > page.rect.width * 0.3 and rect.height > 12:
            exclusions.append(rect)

    return exclusions


def _span_in_exclusion(span_rect: fitz.Rect, exclusions: List[fitz.Rect]) -> bool:
    for ex in exclusions:
        if ex.intersects(span_rect):
            return True
    return False


def extract_visual_lines(page: fitz.Page, page_num: int) -> List[VisualLine]:
    """
    Return a list of VisualLine objects for a single PDF page,
    ordered top-to-bottom.
    """
    exclusions = _get_exclusion_rects(page)

    raw = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
    all_spans = []

    for block in raw.get("blocks", []):
        if block.get("type") != 0:   # type 0 = text block
            continue
        for line in block.get("lines", []):
            # STRICT VISIBILITY CHECK: entire line must have real ink.
            # _has_visible_ink() strips whitespace AND garbage Unicode (U+FFFD)
            # so corrupt OCR glyphs cannot inflate the line count.
            line_content = "".join(span.get("text", "") for span in line.get("spans", []))
            if not _has_visible_ink(line_content):
                continue

            for span in line.get("spans", []):
                text = span.get("text", "")
                if not _has_visible_ink(text):   # also filter span-level garbage
                    continue
                bbox = fitz.Rect(span["bbox"])
                if _span_in_exclusion(bbox, exclusions):
                    continue
                all_spans.append({
                    "text": text,
                    "bbox": bbox,
                    "size": span.get("size", 12),
                    "origin": span.get("origin", (bbox.x0, bbox.y1)),
                })

    if not all_spans:
        return []

    # Sort spans strictly top-to-bottom, then left-to-right
    all_spans.sort(key=lambda s: (s["bbox"].y0, s["bbox"].x0))

    # Group into visual lines by baseline Y proximity.
    # IMPORTANT: use the RUNNING AVERAGE Y of the group as the representative,
    # not just the first span's Y.  Using only the first span causes cumulative
    # drift: if spans A, B, C each shift +2pt from their predecessor, A→B and
    # B→C are both within tolerance but A→C is not — resulting in phantom splits
    # and the irregular counting pattern (10, 8, 7, 9 …) reported by users.
    groups: List[List[dict]] = []   # each item: list of span dicts
    group_avg_y: List[float] = []   # parallel list: running average y0

    for span in all_spans:
        y0 = span["bbox"].y0
        placed = False
        # Check groups in reverse (most recently opened group first)
        for i in range(len(groups) - 1, -1, -1):
            if abs(y0 - group_avg_y[i]) <= BASELINE_TOLERANCE:
                groups[i].append(span)
                # Update running average
                n = len(groups[i])
                group_avg_y[i] = group_avg_y[i] * (n - 1) / n + y0 / n
                placed = True
                break
            # If we've gone more than 2× tolerance above current span, stop searching
            if group_avg_y[i] < y0 - BASELINE_TOLERANCE * 2:
                break
        if not placed:
            groups.append([span])
            group_avg_y.append(y0)

    # Build VisualLine objects
    visual_lines: List[VisualLine] = []
    for idx, group in enumerate(groups):
        y0_vals = [s["bbox"].y0 for s in group]
        y1_vals = [s["bbox"].y1 for s in group]
        yo_vals = [s["origin"][1] for s in group]
        x0_vals = [s["bbox"].x0 for s in group]
        x1_vals = [s["bbox"].x1 for s in group]

        vl = VisualLine(
            page_num=page_num,
            line_num=idx + 1,
            y_baseline=min(y0_vals),
            y_origin=max(yo_vals),  # Use the lowest baseline in the group
            y_bottom=max(y1_vals),
            x_start=min(x0_vals),
            x_end=max(x1_vals),
            spans=group,
        )
        visual_lines.append(vl)

    return visual_lines
