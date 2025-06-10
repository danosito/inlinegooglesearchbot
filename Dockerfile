# ─ Base image ────────────────────────────────────────────────────
FROM python:3.12-slim

# ─ System deps (build + runtime) ─────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential gcc \
    && rm -rf /var/lib/apt/lists/*

# ─ Python deps ───────────────────────────────────────────────────
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ─ Copy bot code ─────────────────────────────────────────────────
COPY . .

# ─ Launch ────────────────────────────────────────────────────────
CMD ["python", "main.py"]
