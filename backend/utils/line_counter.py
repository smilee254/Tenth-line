"""
line_counter.py — Visual line detection using PyMuPDF span bounding boxes.

Strategy:
  1. Extract all text spans from a page via page.get_text("rawdict").
  2. Group spans whose baseline Y values fall within BASELINE_TOLERANCE of each other.
  3. Sort groups top-to-bottom → these are the visual lines.
  4. Optionally exclude spans that fall inside image/table bounding boxes.
"""

from dataclasses import dataclass, field
from typing import List, Tuple
import fitz  # PyMuPDF


BASELINE_TOLERANCE = 2.5  # points; spans within this Y-range share a visual line


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
            # STRICT VISIBILITY CHECK: Does this entire line have 'ink'?
            # We join all spans in the line and strip it. If empty, skip the line.
            line_content = "".join([span.get("text", "") for span in line.get("spans", [])])
            if not line_content.strip():
                continue

            for span in line.get("spans", []):
                text = span.get("text", "")
                if not text.strip():
                    continue
                bbox = fitz.Rect(span["bbox"])
                is_excluded = _span_in_exclusion(bbox, exclusions)
                if is_excluded:
                    continue
                all_spans.append({
                    "text": text,
                    "bbox": bbox,
                    "size": span.get("size", 12),
                    "origin": span.get("origin", (bbox.x0, bbox.y1)),
                })

    if not all_spans:
        return []

    # Sort spans top-to-bottom, left-to-right
    all_spans.sort(key=lambda s: (round(s["bbox"].y0 / BASELINE_TOLERANCE), s["bbox"].x0))

    # Group into visual lines by baseline Y proximity
    groups: List[List[dict]] = []
    for span in all_spans:
        y0 = span["bbox"].y0
        placed = False
        for group in reversed(groups):
            rep_y0 = group[0]["bbox"].y0
            if abs(y0 - rep_y0) <= BASELINE_TOLERANCE:
                group.append(span)
                placed = True
                break
        if not placed:
            groups.append([span])

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
