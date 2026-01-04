# Sakura V10 Backend Dockerfile
FROM python:3.11-slim

# Set environment
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV APP_HOME=/app

WORKDIR $APP_HOME

# Install system dependencies
# - build-essential: for compiling python extensions
# - libportaudio2: for audio support
# - tesseract-ocr: for screen reading
# - curl: for healthcheck
RUN apt-get update && apt-get install -y \
    build-essential \
    libportaudio2 \
    libsndfile1 \
    flac \
    ffmpeg \
    tesseract-ocr \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements-docker.txt .
RUN pip install --no-cache-dir -r requirements-docker.txt

# Copy source code
COPY . .

# Create data directories (volume mount points)
RUN mkdir -p data Notes

# Expose API port
EXPOSE 8000

# Run commands
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
