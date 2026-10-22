FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy project metadata first (better layer caching)
COPY pyproject.toml README.md LICENSE ./

# Copy source and config
COPY src/ src/
COPY config/ config/

RUN pip install --no-cache-dir .

EXPOSE 8080

CMD ["python", "-m", "bacnet_lab"]
