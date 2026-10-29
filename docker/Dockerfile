FROM python:3.12-slim

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Copy project definition and install dependencies
COPY pyproject.toml README.md ./
RUN uv pip install --system --no-cache ".[dev]" greenlet

# Copy application source code (cache-bust: rebuild on every deploy)
ARG RENDER_GIT_COMMIT=unknown
RUN echo "deploying commit=$RENDER_GIT_COMMIT build=$(date +%s 2>/dev/null || echo 0)" > /tmp/build_info.txt && cat /tmp/build_info.txt
COPY app/ ./app/
COPY static/ ./static/
COPY docs/ ./docs/

# Create non-root user and directories
RUN useradd -m -u 1000 appuser && \
    mkdir -p data uploads prompts && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD sh -c "curl -f http://localhost:${PORT:-8000}/health || exit 1"

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
