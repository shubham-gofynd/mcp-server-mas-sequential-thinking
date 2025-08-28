# Use Debian slim so we can install Node + Python easily
FROM python:3.11-slim

# Prevent .pyc and buffering
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Install system deps + Node.js (for npx)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl gnupg build-essential git \
 && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
 && apt-get install -y nodejs \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy your repo code
COPY . /app

# Install Python deps
RUN pip install --upgrade pip && pip install .

# Install mcp-remote globally
RUN npm install -g mcp-remote

# Run your stdio server wrapped by mcp-remote
CMD ["mcp-remote", "python", "main.py"]
