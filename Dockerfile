FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off

WORKDIR /app

# System build deps (kept minimal; adjust if you add native deps later)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
 && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first for better Docker layer caching
COPY requirements.txt pyproject.toml ./
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir .

# Copy the rest of the application code
COPY . .

# By default, FastAPI/uvicorn will listen on 8000
EXPOSE 8000

# Environment variables like:
# - SIMRAI_SPOTIFY_CLIENT_ID
# - SIMRAI_SPOTIFY_CLIENT_SECRET
# - SIMRAI_SPOTIFY_REDIRECT_URI
# - GROQ_API_KEY
# should be provided at runtime (e.g. via docker run -e or your orchestrator).

CMD ["uvicorn", "simrai.api:app", "--host", "0.0.0.0", "--port", "8000"]


