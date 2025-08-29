# Dockerfile — FastMCP HTTP server (no proxy)
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential git curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

# Install your project and its deps
# If you have requirements.txt, prefer: pip install -r requirements.txt
RUN python -m pip install --upgrade pip && pip install .

# Boltic typically maps to a port; use 8080 as default
EXPOSE 8080

# Defaults for serverless
ENV MCP_TRANSPORT=http \
    HOST=0.0.0.0 \
    PORT=8080

# Run your server; FastMCP serves MCP at /mcp/
CMD ["python", "main.py"]
