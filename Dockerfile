FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# System dependencies for lxml, BeautifulSoup, unstructured, PDF export
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libxml2-dev \
    libxslt-dev \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# Install CPU-only torch first to avoid pulling CUDA packages (~2GB) on a small server
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# data/ is mounted as a volume — create empty dirs so app doesn't crash on first run
RUN mkdir -p data/inbox data/processed data/vector_db data/exports \
             data/intel data/logs data/backups

CMD ["python", "bot.py"]
