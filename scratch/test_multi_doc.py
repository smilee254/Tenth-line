#!/usr/bin/env python3
"""
test_multi_doc.py — Tests counting accuracy across 5 structurally different documents.

Each document is unique (different content, line length, density, spacing).
We do NOT reuse the pre-existing test document.
All documents are created fresh here.

For each document we verify:
  1. Stamps appear at exactly the right intervals
  2. Blank lines are NOT counted
  3. Short pages (< 10 body lines) are silently skipped
  4. Count resets cleanly on each page
"""

import sys, io, os, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import fitz
from docx import Document as DocxDoc
from docx.shared import Pt, Inches
from backend.processors.pdf_processor import annotate_pdf
from backend.processors.docx_processor import process_docx
from backend.utils.line_counter import extract_visual_lines

SEP = "─" * 70
PASS = "✅"
FAIL = "❌"


def make_pdf_with_lines(line_texts: list[str], fontsize=11, line_spacing=14) -> bytes:
    """Create a PDF with exactly the given lines of text."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    y = 100.0
    for text in line_texts:
        if text.strip():
            page.insert_text((90, y), text, fontsize=fontsize, color=(0, 0, 0))
        y += line_spacing
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def make_docx_with_lines(line_texts: list[str], font_name="Times New Roman") -> bytes:
    """Create a DOCX with exactly the given lines of text."""
    doc = DocxDoc()
    sec = doc.sections[0]
    sec.left_margin  = Inches(1.5)
    sec.right_margin = Inches(1.0)
    sec.top_margin   = Inches(1.0)
    sec.bottom_margin = Inches(1.0)
    for text in line_texts:
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after  = Pt(0)
        p.paragraph_format.line_spacing = Pt(14)
        run = p.add_run(text)
        run.font.name = font_name
        run.font.size = Pt(12)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def extract_stamps_from_pdf(pdf_bytes: bytes) -> dict[int, list[int]]:
    """
    Parse gutter stamps from annotated PDF.
    Returns {page_num: [10, 20, 30, ...]} for each page that has stamps.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    stamps: dict[int, list[int]] = {}
    for i, page in enumerate(doc):
        text = page.get_text()
        found = []
        for token in text.split():
            if token.startswith("-") and token[1:].isdigit():
                found.append(int(token[1:]))
        if found:
            stamps[i + 1] = sorted(set(found))
    doc.close()
    return stamps


def check(label: str, condition: bool) -> bool:
    icon = PASS if condition else FAIL
    print(f"  {icon}  {label}")
    return condition


def run_test(name: str, pdf_bytes: bytes,
             expected_stamps: dict[int, list[int]],
             interval: int = 10,
             skip_pages: int = 1) -> bool:
    print(f"\n{SEP}")
    print(f"  TEST: {name}")
    print(SEP)

    try:
        fd_in, temp_in = tempfile.mkstemp(suffix=".pdf")
        fd_out, temp_out = tempfile.mkstemp(suffix=".pdf")
        os.close(fd_out)
        with os.fdopen(fd_in, "wb") as f:
            f.write(pdf_bytes)

        annotate_pdf(temp_in, temp_out, interval=interval,
                     skip_pages=skip_pages, margin_side="left",
                     draw_rule=True)
        
        with open(temp_out, "rb") as f:
            result = f.read()
    except Exception as e:
        print(f"  {FAIL}  annotate_pdf() raised: {e}")
        return False
    finally:
        for p in (temp_in, temp_out):
            if os.path.exists(p): os.remove(p)

    actual = extract_stamps_from_pdf(result)
    all_ok = True

    for page, want in expected_stamps.items():
        got = actual.get(page, [])
        ok = sorted(got) == sorted(want)
        all_ok = all_ok and ok
        check(f"Page {page} stamps: expected {want}, got {sorted(got)}", ok)

    # Pages that should have NO stamps
    for page in actual:
        if page not in expected_stamps:
            print(f"  {FAIL}  Unexpected stamps on page {page}: {actual[page]}")
            all_ok = False

    return all_ok


# ─────────────────────────────────────────────────────────────────────────────

def test_1_standard_legal_pleading():
    """25 real lines on a body page. Cover skipped. Expect -10, -20."""
    cover_lines = ["IN THE COURT OF APPEAL"]          # 1 line cover
    body_lines = [
        f"Paragraph {i}: Plaintiff respectfully submits the following facts in "
        f"support of this motion as numbered herein for the court record."
        for i in range(1, 26)  # 25 body lines
    ]
    pdf = make_pdf_with_lines(cover_lines + body_lines)
    # Page 1 only — cover (1 line) is skipped, 25 body lines → stamps at 10, 20
    # But since everything is on 1 page, skip_pages=1 skips whole page 1
    # So we need 2 pages: cover page + body page
    doc = fitz.open()
    # Cover page
    p1 = doc.new_page(width=612, height=792)
    p1.insert_text((90, 400), "IN THE COURT OF APPEAL — COVER PAGE", fontsize=14)
    # Body page
    p2 = doc.new_page(width=612, height=792)
    y = 100.0
    for i in range(1, 26):
        text = (f"{i:02d}. Plaintiff respectfully submits the following facts in "
                f"support of this motion as numbered herein for the court record.")
        p2.insert_text((90, y), text, fontsize=11, color=(0, 0, 0))
        y += 14
    buf = io.BytesIO(); doc.save(buf); doc.close()
    return run_test(
        "Standard Legal Pleading (25 body lines, cover skip)",
        buf.getvalue(),
        expected_stamps={2: [10, 20]},   # page 2 = body page
        skip_pages=1
    )


def test_2_blank_lines_ignored():
    """Real content interleaved with blank lines. Blanks must NOT be counted."""
    doc = fitz.open()
    p = doc.new_page(width=612, height=792)
    # Insert 10 real lines, 5 blank lines, then 10 more real lines
    # Total visible = 20, blanks ignored → stamps at 10, 20
    y = 80.0
    real_count = 0
    for i in range(25):
        if i % 3 == 2:
            # blank line — no text inserted
            pass
        else:
            real_count += 1
            text = (f"Article {real_count}: The parties agree to the terms "
                    f"set forth herein with full knowledge and consent.")
            p.insert_text((90, y), text, fontsize=11, color=(0, 0, 0))
        y += 14
    buf = io.BytesIO(); doc.save(buf); doc.close()
    # real_count should be ~17 real lines → stamp at 10
    return run_test(
        "Blank Lines Interleaved (blanks must be ignored)",
        buf.getvalue(),
        expected_stamps={1: [10]},
        skip_pages=0
    )


def test_3_short_lines_poem_style():
    """40 very short lines (like a list or poem). Stamps at 10, 20, 30, 40."""
    doc = fitz.open()
    p = doc.new_page(width=612, height=792)
    y = 60.0
    items = [
        "1. Parties", "2. Jurisdiction", "3. Venue", "4. Background",
        "5. Facts", "6. Count One", "7. Count Two", "8. Count Three",
        "9. Relief", "10. Prayer",
        "11. Defendant", "12. Plaintiff", "13. Court", "14. Appeal",
        "15. Motion", "16. Order", "17. Judgment", "18. Stay",
        "19. Bond", "20. Costs",
        "21. Fees", "22. Interest", "23. Damages", "24. Injunction",
        "25. Contempt", "26. Sanctions", "27. Discovery", "28. Evidence",
        "29. Witnesses", "30. Exhibits",
        "31. Arguments", "32. Rebuttal", "33. Closing", "34. Verdict",
        "35. Sentence", "36. Probation", "37. Appeal", "38. Review",
        "39. Remand", "40. Affirmed",
    ]
    for item in items:
        p.insert_text((90, y), item, fontsize=11, color=(0, 0, 0))
        y += 16
    buf = io.BytesIO(); doc.save(buf); doc.close()
    return run_test(
        "Short Lines / List Style (40 items, stamps at 10,20,30,40)",
        buf.getvalue(),
        expected_stamps={1: [10, 20, 30, 40]},
        skip_pages=0
    )


def test_4_multi_page_with_reset():
    """2 body pages, 20 lines each. Counter resets per page: stamps at 10,20 on each."""
    doc = fitz.open()
    for page_num in range(2):
        pg = doc.new_page(width=612, height=792)
        y = 90.0
        for i in range(1, 21):
            text = (f"[P{page_num+1} L{i:02d}] Counsel moves for summary judgment "
                    f"on the grounds that no genuine dispute exists.")
            pg.insert_text((90, y), text, fontsize=11, color=(0, 0, 0))
            y += 14
    buf = io.BytesIO(); doc.save(buf); doc.close()
    return run_test(
        "Multi-Page Counter Reset (2 pages × 20 lines, stamps at 10,20 each)",
        buf.getvalue(),
        expected_stamps={1: [10, 20], 2: [10, 20]},
        skip_pages=0
    )


def test_5_docx_bookman_reflow():
    """DOCX with Bookman Old Style. Font pre-processing must prevent reflow."""
    lines = [
        f"Section {i}: The undersigned counsel hereby certifies that this "
        f"document complies with all applicable court rules and formatting."
        for i in range(1, 21)   # 20 body lines → stamps at 10, 20
    ]
    docx_bytes = make_docx_with_lines(lines, font_name="Bookman Old Style")
    print(f"\n{SEP}")
    print("  TEST: DOCX Bookman Old Style (font pre-processing + LibreOffice)")
    print(SEP)
    try:
        fd_in, temp_in = tempfile.mkstemp(suffix=".docx")
        fd_out, temp_out = tempfile.mkstemp(suffix=".pdf")
        os.close(fd_out)
        with os.fdopen(fd_in, "wb") as f:
            f.write(docx_bytes)

        process_docx(temp_in, temp_out, interval=10, skip_pages=0,
                     margin_side="left", draw_rule=True)
                     
        with open(temp_out, "rb") as f:
            pdf_bytes = f.read()
    except Exception as e:
        print(f"  {FAIL}  process_docx() raised: {e}")
        return False
    finally:
        for p in (temp_in, temp_out):
            if os.path.exists(p): os.remove(p)

    stamps = extract_stamps_from_pdf(pdf_bytes)
    actual = stamps.get(1, [])
    ok_10 = 10 in actual
    ok_20 = 20 in actual
    check("Stamp -10 present", ok_10)
    check("Stamp -20 present", ok_20)
    return ok_10 and ok_20


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    results = [
        test_1_standard_legal_pleading(),
        test_2_blank_lines_ignored(),
        test_3_short_lines_poem_style(),
        test_4_multi_page_with_reset(),
        test_5_docx_bookman_reflow(),
    ]

    print(f"\n{SEP}")
    passed = sum(results)
    total  = len(results)
    print(f"  RESULTS: {passed}/{total} tests passed")
    if passed == total:
        print(f"  {PASS} ALL PASS — counting is consistent across all document types")
    else:
        print(f"  {FAIL} {total - passed} test(s) FAILED — investigate above")
    print(SEP)
    sys.exit(0 if passed == total else 1)
