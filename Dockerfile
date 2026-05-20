FROM python:3.11-slim

# Install LibreOffice for DOCX → PDF conversion
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libreoffice \
        fonts-liberation \
        && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY frontend/ ./frontend/

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
