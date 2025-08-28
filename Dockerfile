# Use a fuller image; Alpine + wheels often hurts build time
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# System deps (adjust if any lib complains)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates build-essential git \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the whole repo so config.py and everything is present
COPY . /app

# Install deps (choose whichever your repo uses)
# If you have requirements.txt:
# RUN pip install -r requirements.txt
# If you use pyproject.toml (PEP 517):
RUN pip install --upgrade pip && pip install .

# Ensure repo root is importable for `import config`
ENV PYTHONPATH=/app

# Run *from the repo*, not the installed console_script
# (so main.py can import local config.py)
CMD ["python", "main.py"]

