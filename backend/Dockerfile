# Sakura V10 Backend - Docker Image
# Optimized for API-only deployment (frontend runs separately)

FROM python:3.11-slim

# Install system dependencies for voice/screen features
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    curl \
    # Optional: Tesseract for screen reading
    tesseract-ocr \
    # Optional: PortAudio for pyaudio (voice)
    portaudio19-dev \
    # Cleanup
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy and install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Environment
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV SAKURA_PORT=8000

# Runtime configuration via env vars:
# - GROQ_API_KEY (required)
# - OPENROUTER_API_KEY (optional, for vision)
# - TAVILY_API_KEY (optional, for web search)

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run (without voice - Docker doesn't have mic access)
CMD ["python", "server.py"]
