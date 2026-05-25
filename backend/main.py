from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from backend.routers.process import router as process_router
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from backend.core.security import limiter

app = FastAPI(title='Tenthline', description='Court-ready document line numbering', version='1.0.0')
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'])
app.include_router(process_router)

@app.get('/api/health', tags=['meta'])
async def health():
    return {'status': 'ok', 'service': 'tenthline'}

FRONTEND_DIR = Path(__file__).parent.parent / 'frontend'
if FRONTEND_DIR.exists():
    app.mount('/', StaticFiles(directory=str(FRONTEND_DIR), html=True), name='frontend')