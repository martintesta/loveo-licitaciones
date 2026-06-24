# Imagen para hostear el tablero (Streamlit) en Render u otro PaaS/VPS.
# La base de datos es Neon (Postgres) vía DATABASE_URL; la descarga de bases (Capa B) corre
# en el worker residencial aparte, así que acá NO instalamos Playwright/Chromium.
FROM python:3.11-slim

WORKDIR /app

# OCR opcional para la Capa C (PDFs escaneados). Si no lo querés, quitá esta línea.
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr tesseract-ocr-spa \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1
EXPOSE 8501

# Render inyecta $PORT. address 0.0.0.0 para aceptar tráfico externo.
CMD streamlit run tablero3.py \
    --server.port ${PORT:-8501} \
    --server.address 0.0.0.0 \
    --server.headless true
