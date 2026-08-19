# ArchiAI building engine -- HTTP service
#
# The engine is pure standard-library Python; everything installed here is for
# the web layer. Build context is the repository root:
#     docker build -f deploy/Dockerfile -t archiai-engine .
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src \
    ARCHIAI_STORAGE=supabase \
    ARCHIAI_TMP=/tmp/archiai-gen \
    PORT=8080

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

RUN useradd --create-home --uid 10001 archiai && \
    mkdir -p /tmp/archiai-gen && chown -R archiai /tmp/archiai-gen
USER archiai

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=4s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request,os,sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8080')+'/v1/health', timeout=3).status==200 else 1)"

CMD ["sh", "-c", "uvicorn archiai.service.app:app --host 0.0.0.0 --port ${PORT} --workers ${WEB_CONCURRENCY:-2}"]
