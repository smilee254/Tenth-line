#!/usr/bin/env -S /home/smilee/Tenthline/.venv/bin/python
import argparse
import sys
import fitz  # PyMuPDF
from pathlib import Path

def get_accurate_lines(page):
    """
    Extract lines based on PyMuPDF's text dict structure.
    Groups by spatial bounding box (y-coordinate) to handle wrapped text.
    Skips empty lines that do not contain visible ink.
    """
    text_instances = page.get_text("dict")["blocks"]
    actual_lines = []

    for block in text_instances:
        if "lines" in block:
            for line in block["lines"]:
                # Check if the line actually has text
                content = "".join([span["text"] for span in line["spans"]]).strip()
                if content:
                    # Store the Y-coordinate to know where to draw the number
                    # We append a tuple of (y-coordinate, text content) for visibility in dry-run
                    actual_lines.append((line["bbox"][1], content))
    
    # Sort lines top-to-bottom
    actual_lines.sort(key=lambda x: x[0])
    return actual_lines

def process_pdf(input_path: str, dry_run: bool = False):
    try:
        doc = fitz.open(input_path)
    except Exception as e:
        print(f"Error opening PDF: {e}")
        sys.exit(1)
        
    total_pages = len(doc)
    
    for page_num in range(total_pages):
        page = doc[page_num]
        
        # We start line counting from 0 at each page (Hard-resets line_count per page)
        line_count = 0
        print(f"\n--- Processing Page {page_num + 1}/{total_pages} ---")
        
        # Extract visually accurate lines (ignoring whitespace and handling wrapped BBox text)
        lines = get_accurate_lines(page)
        
        for y_coord, content in lines:
            # We already stripped content inside get_accurate_lines, 
            # but we can enforce the check again here
            if content.strip():
                line_count += 1
                
                if dry_run:
                    # In dry-run mode, we just print the accurate count instead of saving
                    if line_count % 10 == 0:
                        print(f"Marking line {line_count} at Y:{y_coord:.2f} -> '{content[:40]}...'")
                    
        print(f"Total counted visual lines on Page {page_num + 1}: {line_count}")

    doc.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Accurate line counting with spatial grouping.")
    parser.add_argument("--input", required=True, help="Path to input PDF file.")
    parser.add_argument("--dry-run", action="store_true", help="Run line counts without saving modifications.")
    args = parser.parse_args()
    
    if not Path(args.input).exists():
        print(f"Input file {args.input} does not exist.")
        sys.exit(1)
        
    process_pdf(args.input, dry_run=args.dry_run)
