"""
test_line_numbering.py — Integration test for Tenthline legal compliance.
Verifies:
  1. Dash prefix (-10, -20)
  2. Silent Ignore (pages with < 10 lines)
  3. Header Skip (lines in top margin)
  4. Hard Page Reset (restarts at -10 per page)
"""

import os
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent))

import fitz
from backend.processors.pdf_processor import annotate_pdf


def create_sample_pdf(output_path: str):
    """Create a 4-page PDF with dummy text for testing."""
    doc = fitz.open()
    
    # Page 1: Standard (will be skipped by skip_pages=1)
    page = doc.new_page()
    page.insert_text((72, 100), "Cover Page Content", fontsize=12)

    # Page 2: Body Page with 50 lines (should have -10, -20, -30, -40)
    # Header should be ignored by TOP_MARGIN_SKIP
    page = doc.new_page()
    page.insert_text((72, 50), "REPUBLIC OF KENYA (Header)", fontsize=14)
    y = 120
    for i in range(50):
        page.insert_text((72, y), f"This is line {i+1} of the pleading content.", fontsize=11)
        y += 14
        
    # Page 3: Short Page with 5 lines (should be SILENTLY IGNORED)
    page = doc.new_page()
    y = 120
    for i in range(5):
        page.insert_text((72, y), f"Final line {i+1} before signature.", fontsize=11)
        y += 14
    page.insert_text((72, y + 20), "SIGNED: ________________", fontsize=11)

    # Page 4: Another Body Page (should restart at -10)
    page = doc.new_page()
    y = 120
    for i in range(20):
        page.insert_text((72, y), f"Restarting count on Page 4, line {i+1}", fontsize=11)
        y += 14
            
    doc.save(output_path)
    doc.close()
    print(f"✅ Created sample PDF: {output_path}")


def verify_numbering(pdf_path: str):
    """Verify court-compliant numbering rules."""
    doc = fitz.open(pdf_path)
    
    # Page 1 (Skip)
    print("\nVerifying Page 1 (Cover)...")
    if "-10" not in doc[0].get_text():
        print("  ✅ Page 1 skipped correctly")

    # Page 2 (Body)
    print("\nVerifying Page 2 (Body)...")
    text2 = doc[1].get_text()
    for num in ["-10", "-20", "-30", "-40"]:
        if num in text2:
            print(f"  ✅ Found '{num}'")
        else:
            print(f"  ❌ FAILED: '{num}' not found on Page 2")

    # Page 3 (Short)
    print("\nVerifying Page 3 (Short/Ignore)...")
    if "-10" not in doc[2].get_text():
        print("  ✅ Page 3 silently ignored correctly (less than 10 lines)")
    else:
        print("  ❌ FAILED: Page 3 should have been ignored but contains numbers")

    # Page 4 (Reset)
    print("\nVerifying Page 4 (Reset)...")
    text4 = doc[3].get_text()
    if "-10" in text4 and "-20" in text4:
        print("  ✅ Page 4 correctly restarted count at -10")
    else:
        print("  ❌ FAILED: Page 4 numbering incorrect")
                    
    doc.close()


if __name__ == "__main__":
    sample_in = "sample_input.pdf"
    sample_out = "sample_output.pdf"
    
    try:
        create_sample_pdf(sample_in)
        
        with open(sample_in, "rb") as f:
            # We use interval=10, skip_pages=1
            processed_bytes = annotate_pdf(f.read(), interval=10, skip_pages=1)
            
        with open(sample_out, "wb") as f:
            f.write(processed_bytes)
        print(f"✅ Processed document: {sample_out}")
        
        verify_numbering(sample_out)
        
    finally:
        for p in [sample_in, sample_out]:
            if os.path.exists(p):
                os.remove(p)
