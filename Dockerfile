# Lightweight & stable base with Python + apt
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# System deps (build tools often needed by Py deps)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential git curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy entire repo so config.py and others are present
COPY . /app

# Install your project (adjust if you use requirements.txt/poetry/uv)
RUN pip install --upgrade pip && pip install .

# Install the stdio<->HTTP/SSE bridge
# PyPI name: mcp-proxy (a.k.a. mcp-http-stdio-bridge)
RUN pip install mcp-proxy

# Ensure the repo root is importable (for `from config import ...`)
ENV PYTHONPATH=/app

# EXPOSE is optional for Boltic, but good documentation
EXPOSE 8080

# Run a local stdio server (python main.py) behind an HTTP/SSE proxy
# --pass-environment forwards all env vars (DEEPSEEK_API_KEY, EXA_API_KEY, etc)
# --host 0.0.0.0 listens on container interface so Boltic can reach it
# Bridge serves:
#   - Streamable HTTP: http://0.0.0.0:8080/mcp
#   - SSE:             http://0.0.0.0:8080/sse
CMD ["mcp-proxy", "--pass-environment", "--host", "0.0.0.0", "--port", "8080", "python", "main.py"]
