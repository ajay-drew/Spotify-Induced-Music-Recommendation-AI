FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off

WORKDIR /app

# System build deps (kept minimal; adjust if you add native deps later)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
 && rm -rf /var/lib/apt/lists/*

# Copy the full project into the image so setuptools can see the 'src' package layout
COPY . .

# Install Python dependencies and the local package
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir .

# By default, FastAPI/uvicorn will listen on 8000
EXPOSE 8000

# Environment variables like:
# - SIMRAI_SPOTIFY_CLIENT_ID
# - SIMRAI_SPOTIFY_CLIENT_SECRET
# - GROQ_API_KEY
# should be provided at runtime (e.g. via docker run -e or your orchestrator).

CMD ["uvicorn", "simrai.api:app", "--host", "0.0.0.0", "--port", "8000"]


