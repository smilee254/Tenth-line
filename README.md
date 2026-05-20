# Tenthline

> Court-ready tenth-line document numbering — PDF & DOCX

Tenthline automatically detects every **visual line** in a document (including wrapped text) and stamps the left or right margin with line numbers at every 10th line, exactly as required by most court filing rules.

---

## Features

- **PDF & DOCX** input support
- **Visual line detection** — counts wrapped lines correctly, not just `\n` characters
- **Skips cover pages** — configurable number of leading pages to leave unnumbered
- **Left or right margin** numbering
- **Optional gutter rule** — faint vertical line for a professional finish
- **In-browser preview** — see the result before downloading
- **In-memory processing** — files are never written to disk on the server

---

## Requirements

| Dependency | Purpose |
|---|---|
| Python 3.10+ | Backend runtime |
| LibreOffice | DOCX → PDF conversion (headless) |

### Install LibreOffice

```bash
# Ubuntu / Debian
sudo apt install libreoffice

# macOS
brew install --cask libreoffice

# Fedora / RHEL
sudo dnf install libreoffice
```

---

## Quick Start

```bash
git clone <repo-url>
cd Tenthline
chmod +x run.sh
./run.sh
```

Then open **http://localhost:8000** in your browser.

The script will:
1. Create a Python virtual environment in `.venv/`
2. Install all Python dependencies
3. Launch the server with hot-reload enabled

---

## Manual Setup

```bash
cd Tenthline
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload --port 8000
```

---

## Docker

```bash
docker build -t tenthline .
docker run -p 8000:8000 tenthline
```

---

## API Reference

### `POST /api/process`

Upload a document and receive an annotated PDF.

**Form fields:**

| Field | Type | Default | Description |
|---|---|---|---|
| `file` | File | — | `.pdf` or `.docx` upload |
| `interval` | int | `10` | Number every N-th line |
| `skip_pages` | int | `1` | Pages to leave unnumbered from front |
| `margin_side` | str | `"left"` | `"left"` or `"right"` |
| `draw_rule` | bool | `true` | Draw faint vertical gutter rule |

**Response:** `application/pdf` binary stream

---

## Project Structure

```
Tenthline/
├── backend/
│   ├── main.py                    # FastAPI app
│   ├── requirements.txt
│   ├── routers/
│   │   └── process.py             # /api/process endpoint
│   ├── processors/
│   │   ├── pdf_processor.py       # PDF annotation engine
│   │   └── docx_processor.py      # DOCX → PDF pipeline
│   └── utils/
│       └── line_counter.py        # Visual line detection algorithm
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── app.js
├── Dockerfile
└── run.sh
```

---

## How Visual Line Detection Works

1. **Span extraction** — PyMuPDF's `page.get_text("rawdict")` returns every text span with its bounding box `(x0, y0, x1, y1)`.
2. **Baseline grouping** — Spans whose `y0` values fall within ±2.5 pt of each other are merged into one visual line. This correctly handles text that wraps at the margin.
3. **Exclusions** — Image blocks and large filled rectangles (table backgrounds) are detected and skipped so numbering pauses around non-text content.
4. **Stamping** — At every line where `line_number % interval == 0`, a small grey number is drawn at a fixed X coordinate in the gutter margin.

---

## Edge Cases

| Situation | Handling |
|---|---|
| Cover / title pages | Controlled by `skip_pages` (default: skip page 1) |
| Wrapped text | Baseline-Y grouping prevents double-counting |
| Tables | Detected via block type and rect heuristics; numbering pauses |
| Images / figures | Block type `1` spans are excluded |
| Mixed font sizes | Grouping is Y-based, not font-size-based |
