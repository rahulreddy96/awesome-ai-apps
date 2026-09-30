FROM python:3.11-slim AS base

RUN apt-get update && \
    apt-get install -y --no-install-recommends git curl && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY cloud_deploy/requirements.txt /app/cloud_deploy/requirements.txt
RUN uv pip install --system --no-cache -r /app/cloud_deploy/requirements.txt

COPY . /app

ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    CLOUD_TIER=minimal

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

ENTRYPOINT ["python", "-m", "cloud_deploy.run"]
