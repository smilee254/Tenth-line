import os
import shutil
import tempfile
from fastapi import APIRouter, File, Form, HTTPException, UploadFile, Request, Depends
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool
from backend.core.engine import annotate_pdf, process_docx
from backend.core.security import limiter, verify_api_key

router = APIRouter(prefix='/api', tags=['process'], dependencies=[Depends(verify_api_key)])

ALLOWED_TYPES = {
    'application/pdf': 'pdf',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
    'application/octet-stream': None,
}


def _detect_file_type(filename: str, content_type: str) -> str:
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    if ext == 'pdf':
        return 'pdf'
    if ext == 'docx':
        return 'docx'
    if content_type in ALLOWED_TYPES and ALLOWED_TYPES[content_type]:
        return ALLOWED_TYPES[content_type]
    raise HTTPException(status_code=422, detail=f"Unsupported file type '{ext}'. Please upload a .pdf or .docx file.")


def _cleanup_files(*paths: str):
    for path in paths:
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass


@router.post('/process')
@limiter.limit("10/minute")
async def process_document(
    request: Request,
    file: UploadFile = File(...),
    interval: int = Form(10, ge=1, le=100),
    skip_pages: int = Form(1, ge=0, le=50),
    margin_side: str = Form('left', pattern="^(left|right)$"),
    draw_rule: bool = Form(True),
    excluded_signatures: str = Form('', max_length=500),
):
    if not file.filename:
        raise HTTPException(status_code=422, detail='Uploaded file has no filename.')
    file_type = _detect_file_type(file.filename or '', file.content_type or '')
    
    # Validation handled mostly by FastAPI Form constraints now
    signatures_list = [sig.strip() for sig in excluded_signatures.split(',') if sig.strip()]

    fd_in, temp_in = tempfile.mkstemp(suffix=f'.{file_type}')
    with os.fdopen(fd_in, 'wb') as f_in:
        shutil.copyfileobj(file.file, f_in)
    fd_out, temp_out = tempfile.mkstemp(suffix='.pdf')
    os.close(fd_out)
    try:
        if file_type == 'pdf':
            await run_in_threadpool(annotate_pdf, temp_in, temp_out, interval=interval, skip_pages=skip_pages, margin_side=margin_side, draw_rule=draw_rule, excluded_signatures=signatures_list)
        else:
            await run_in_threadpool(process_docx, temp_in, temp_out, interval=interval, skip_pages=skip_pages, margin_side=margin_side, draw_rule=draw_rule, excluded_signatures=signatures_list)
    except Exception as e:
        _cleanup_files(temp_in, temp_out)
        raise HTTPException(status_code=500, detail=str(e))
    stem = (file.filename or 'document').rsplit('.', 1)[0]
    download_name = f'{stem}_tenthlined.pdf'
    return FileResponse(
        temp_out,
        media_type='application/pdf',
        filename=download_name,
        headers={'X-Filename': download_name},
        background=BackgroundTask(_cleanup_files, temp_in, temp_out),
    )
