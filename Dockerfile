# Dockerfile — MCP stdio server exposed over HTTP/SSE via mcp-proxy

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# System deps (build tools + git + node/npm optional but handy)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential git curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the whole repo so config.py and modules are available at runtime
COPY . /app

# Install your project (adjust if you use requirements.txt/poetry)
RUN python -m pip install --upgrade pip \
 && pip install .

# Install the stdio↔HTTP/SSE bridge
# (package name: mcp-proxy / mcp-http-stdio-bridge)
RUN pip install mcp-proxy

# Ensure imports like `from config import ...` work from repo root
ENV PYTHONPATH=/app

EXPOSE 8080

# IMPORTANT: Use --transport sse (your mcp-proxy version doesn't accept --sse)
# --pass-environment forwards LLM_PROVIDER, DEEPSEEK_API_KEY, EXA_API_KEY, etc.
# This keeps the server running and exposes:
#   POST /mcp   (JSON-RPC over HTTP)
#   GET  /sse   (Server-Sent Events)
CMD ["mcp-proxy", "--transport", "sse", "--pass-environment", "--host", "0.0.0.0", "--port", "8080", "python", "main.py"]