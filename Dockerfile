FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Install system deps + Node (needed if you later want npx utils)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential git curl ca-certificates nodejs npm \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy full repo (so config.py etc is available)
COPY . /app

# Install your project
RUN pip install --upgrade pip && pip install .

# Install mcp-proxy (stdio→HTTP/SSE bridge)
RUN pip install mcp-proxy

# Ensure repo root is importable
ENV PYTHONPATH=/app

EXPOSE 8080

# Run MCP proxy in SSE mode wrapping your stdio server
CMD ["mcp-proxy", "--sse", "--pass-environment", "--host", "0.0.0.0", "--port", "8080", "python", "main.py"]
