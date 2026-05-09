FROM python:3.11-slim

# Install Node.js 22
RUN apt-get update && apt-get install -y curl && \
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y nodejs && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY setup.py .
COPY majestic/ ./majestic/

RUN pip install -e . --no-cache-dir

COPY profiles/ ./profiles/
COPY data/ ./data/
COPY scripts/ ./scripts/

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["majestic"]
CMD []
