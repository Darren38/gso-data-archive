FROM python:3.12-slim

# postgresql-client provides pg_dump/pg_restore for native backups.
RUN apt-get update \
 && apt-get install -y --no-install-recommends postgresql-client \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
COPY gso_archive ./gso_archive
COPY web ./web
RUN pip install --no-cache-dir -r requirements.txt

RUN useradd --create-home --uid 10001 app && mkdir -p /data/raw /backups && chown -R app /data /backups
USER app

ENV RAW_STORE_DIR=/data/raw PYTHONUNBUFFERED=1
EXPOSE 8000
HEALTHCHECK --interval=60s --timeout=5s CMD python -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4)" || exit 1
CMD ["python", "-m", "gso_archive", "serve", "--host", "0.0.0.0", "--port", "8000"]
