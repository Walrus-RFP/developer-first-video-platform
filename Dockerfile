FROM python:3.10-slim

WORKDIR /app

# Install system dependencies (ffmpeg for HLS encoding, libpq-dev/gcc for PostgreSQL)
RUN apt-get update && apt-get install -y ffmpeg libpq-dev gcc && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Expose ports for both services (mapped in docker-compose)
EXPOSE 8000 8001
