import shutil
import subprocess
import tempfile
import zipfile
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional
import fitz

# --- Constants & Config ---
BASELINE_TOLERANCE = 4.0
_GARBAGE_CHARS = str.maketrans('', '', '\ufffd\x00\xa0')
GUTTER_X_LEFT = 28.0
RULE_LINE_X = 36.0
NUMBER_FONTSIZE = 12.0
NUMBER_COLOR = (0.0, 0.0, 0.0)
RULE_COLOR = (0.75, 0.75, 0.75)
RULE_WIDTH = 0.4
BOOKMAN_PATH = '/usr/share/fonts/opentype/urw-base35/URWBookman-Light.otf'
FONT_SUBSTITUTIONS = {'Bookman Old Style': 'URW Bookman'}
_XML_EXTENSIONS = {'.xml', '.rels'}
SOFFICE_CANDIDATES = [
    'soffice', 'libreoffice', '/usr/bin/soffice',
    '/usr/lib/libreoffice/program/soffice',
    '/Applications/LibreOffice.app/Contents/MacOS/soffice',
]

# --- Line Counting Engine ---
def _has_visible_ink(text: str) -> bool:
    stripped = text.strip()
    if not stripped: return False
    meaningful = stripped.translate(_GARBAGE_CHARS).strip()
    if not meaningful: return False
    for ch in meaningful:
        if unicodedata.category(ch)[0] in ('L', 'N'): return True
    return sum(1 for c in meaningful if not c.isspace()) >= 1

@dataclass
class VisualLine:
    page_num: int
    line_num: int
    y_baseline: float
    y_origin: float
    y_bottom: float
    x_start: float
    x_end: float
    spans: list = field(default_factory=list)

def _get_exclusion_rects(page: fitz.Page) -> List[fitz.Rect]:
    exclusions: List[fitz.Rect] = []
    page_area = page.rect.width * page.rect.height
    for img in page.get_images(full=True):
        for item in page.get_image_rects(img[0]):
            if (item.width * item.height) < (page_area * 0.6):
                exclusions.append(item)
    return exclusions

def extract_visual_lines(page: fitz.Page, page_num: int, excluded_signatures: List[str] = None) -> List[VisualLine]:
    excluded_signatures = excluded_signatures or []
    excluded_lower = [s.strip().lower() for s in excluded_signatures if s.strip()]
    exclusions = _get_exclusion_rects(page)
    raw = page.get_text('dict', flags=fitz.TEXT_PRESERVE_WHITESPACE)
    
    if excluded_lower:
        for block in raw.get('blocks', []):
            if block.get('type') != 0: continue
            block_text = "".join(span.get('text', '') for line in block.get('lines', []) for span in line.get('spans', []))
            if any(sig in block_text.lower() for sig in excluded_lower):
                exclusions.append(fitz.Rect(block['bbox']))

    all_spans = []
    for block in raw.get('blocks', []):
        if block.get('type') != 0: continue
        for line in block.get('lines', []):
            if not _has_visible_ink(''.join(span.get('text', '') for span in line.get('spans', []))): continue
            for span in line.get('spans', []):
                text = span.get('text', '')
                if not _has_visible_ink(text): continue
                bbox = fitz.Rect(span['bbox'])
                if any(ex.intersects(bbox) for ex in exclusions): continue
                all_spans.append({'text': text, 'bbox': bbox, 'size': span.get('size', 12), 'origin': span.get('origin', (bbox.x0, bbox.y1))})
    
    if not all_spans: return []
    all_spans.sort(key=lambda s: (s['origin'][1], s['bbox'].x0))
    groups, group_avg_y = [], []
    for span in all_spans:
        y_base = span['origin'][1]
        placed = False
        for i in range(len(groups) - 1, -1, -1):
            if abs(y_base - group_avg_y[i]) <= BASELINE_TOLERANCE:
                groups[i].append(span)
                n = len(groups[i])
                group_avg_y[i] = group_avg_y[i] * (n - 1) / n + y_base / n
                placed = True
                break
            if group_avg_y[i] < y_base - BASELINE_TOLERANCE * 2: break
        if not placed:
            groups.append([span])
            group_avg_y.append(y_base)
            
    return [VisualLine(
        page_num=page_num, line_num=idx + 1,
        y_baseline=min(s['bbox'].y0 for s in group),
        y_origin=max(s['origin'][1] for s in group),
        y_bottom=max(s['bbox'].y1 for s in group),
        x_start=min(s['bbox'].x0 for s in group),
        x_end=max(s['bbox'].x1 for s in group),
        spans=group
    ) for idx, group in enumerate(groups)]

# --- Annotation Engine ---
def _stamp_number(page: fitz.Page, number: int, y_origin: float, margin_side: str, page_min_x: float) -> None:
    label = f'-{number}'
    pw = page.rect.width
    safe_gutter_x = min(GUTTER_X_LEFT, page_min_x - 12.0)
    font_name = 'bookman'
    try:
        text_width = fitz.get_text_length(label, fontsize=NUMBER_FONTSIZE, fontname=font_name)
    except ValueError:
        text_width = fitz.get_text_length(label, fontsize=NUMBER_FONTSIZE, fontname='helv')
    
    x = max(safe_gutter_x - text_width if margin_side == 'left' else pw - safe_gutter_x + 4, 4.0)
    page.insert_text(fitz.Point(x, y_origin), label, fontsize=NUMBER_FONTSIZE, color=NUMBER_COLOR, fontname=font_name)

def annotate_pdf(input_path: str, output_path: str, interval: int = 10, skip_pages: int = 1, margin_side: str = 'left', draw_rule: bool = True, excluded_signatures: list = None) -> None:
    doc = fitz.open(input_path)
    for page_idx in range(len(doc)):
        if page_idx < skip_pages: continue
        page = doc[page_idx]
        visual_lines = extract_visual_lines(page, page_idx, excluded_signatures=excluded_signatures)
        body_lines = [vl for vl in visual_lines]
        if len(body_lines) < 10: continue
        
        if Path(BOOKMAN_PATH).exists(): page.insert_font(fontfile=BOOKMAN_PATH, fontname='bookman')
        else: page.insert_font(fontname='bookman', fontname_res='ti-ro')
            
        if draw_rule:
            pw, ph = page.rect.width, page.rect.height
            x = RULE_LINE_X if margin_side == 'left' else pw - RULE_LINE_X
            shape = page.new_shape()
            shape.draw_line(fitz.Point(x, 36), fitz.Point(x, ph - 36))
            shape.finish(color=RULE_COLOR, width=RULE_WIDTH)
            shape.commit()
            
        page_min_x = min(vl.x_start for vl in body_lines) if body_lines else GUTTER_X_LEFT
        for idx, vl in enumerate(body_lines, 1):
            if idx % interval == 0:
                _stamp_number(page, idx, vl.y_origin, margin_side, page_min_x=page_min_x)
    
    doc.save(output_path, garbage=4, deflate=True)
    doc.close()

# --- DOCX Conversion Engine ---
def _find_soffice() -> Optional[str]:
    for candidate in SOFFICE_CANDIDATES:
        path = shutil.which(candidate) or (candidate if Path(candidate).exists() else None)
        if path: return path
    return None

def process_docx(input_docx_path: str, output_pdf_path: str, interval: int = 10, skip_pages: int = 1, margin_side: str = 'left', draw_rule: bool = True, excluded_signatures: list = None) -> None:
    soffice = _find_soffice()
    if not soffice: raise RuntimeError('LibreOffice is not installed or not in PATH.')
    
    with tempfile.TemporaryDirectory() as tmpdir:
        preprocessed_docx = Path(tmpdir) / 'preprocessed.docx'
        with zipfile.ZipFile(input_docx_path, 'r') as zin, zipfile.ZipFile(str(preprocessed_docx), 'w', compression=zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if Path(item.filename).suffix.lower() in _XML_EXTENSIONS:
                    try:
                        text = data.decode('utf-8')
                        for win_font, linux_font in FONT_SUBSTITUTIONS.items(): text = text.replace(win_font, linux_font)
                        data = text.encode('utf-8')
                    except Exception: pass
                zout.writestr(item, data)
                
        result = subprocess.run([soffice, '--headless', '--convert-to', 'pdf', '--outdir', tmpdir, str(preprocessed_docx)], capture_output=True, timeout=300)
        if result.returncode != 0: raise RuntimeError(f'LibreOffice conversion failed:\n{result.stderr.decode(errors="replace")}')
        generated_pdf = Path(tmpdir) / 'preprocessed.pdf'
        if not generated_pdf.exists(): raise RuntimeError('LibreOffice did not produce an output PDF.')
        
        temp_pdf = Path(tmpdir) / 'temp.pdf'
        shutil.copy(generated_pdf, temp_pdf)
        annotate_pdf(str(temp_pdf), output_pdf_path, interval=interval, skip_pages=skip_pages, margin_side=margin_side, draw_rule=draw_rule, excluded_signatures=excluded_signatures)
