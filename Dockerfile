# API image: code + Python packages + migrations (+ dbmate to apply them). No data, no secrets:
# settings come from environment variables (docker-compose passes backend/.env).
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# dbmate binary, so this one image can also run the migrations (see the migrate service).
COPY --from=ghcr.io/amacneil/dbmate:2 /usr/local/bin/dbmate /usr/local/bin/dbmate

# Don't run as root: if the app is ever compromised, the attacker isn't root in the container.
RUN useradd --create-home --uid 1000 app

WORKDIR /app

# Packages first, code after: Docker caches each step, so a code change doesn't reinstall packages.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY scripts ./scripts
COPY migrations ./migrations

USER app

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health', timeout=2)"

# --proxy-headers: trust X-Forwarded-* from nginx in front, so client IPs and https are seen correctly.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
