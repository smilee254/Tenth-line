import fitz
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from backend.processors.pdf_processor import annotate_pdf

def create_wide_text_pdf(output_path: str):
    doc = fitz.open()
    page = doc.new_page()
    
    # Standard text
    y = 120
    for i in range(10):
        page.insert_text((72, y), f"This is a standard line of text at x=72.", fontsize=11)
        y += 20
        
    # A wide line that starts further left
    page.insert_text((20, y), "WIDE LINE STARTING AT X=20 TO TEST OVERLAP PREVENTION.", fontsize=11)
    y += 20
    
    for i in range(10):
        page.insert_text((72, y), f"More standard text below the wide line.", fontsize=11)
        y += 20
        
    doc.save(output_path)
    doc.close()

if __name__ == "__main__":
    create_wide_text_pdf("wide_input.pdf")
    with open("wide_input.pdf", "rb") as f:
        processed = annotate_pdf(f.read(), interval=10, skip_pages=0)
    with open("wide_output.pdf", "wb") as f:
        f.write(processed)
    print("✅ Created wide_output.pdf. Please inspect visually.")
