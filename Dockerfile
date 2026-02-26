# Dockerfile
# ─────────────────────────────────────────────────────────────────
# Packages WebPulse AI into a Docker container.
# Render uses this automatically when it detects a Dockerfile.
#
# WHY DOCKER?
#   Docker bundles your app + Python + all libraries into one
#   self-contained "box". It runs identically on any server,
#   eliminating "works on my machine" problems.
#
# HOW IT WORKS (read top to bottom):
#   1. Start from an official Python image
#   2. Copy your project files into the container
#   3. Install all dependencies
#   4. Tell the container how to start the app
# ─────────────────────────────────────────────────────────────────

# Step 1: Base image
# python:3.11-slim = Python 3.11 with minimal extras (smaller = faster deploy)
FROM python:3.11-slim

# Step 2: Set working directory inside the container
# All commands below run from this folder
WORKDIR /app

# Step 3: Install system dependencies
# These are needed by lxml (the HTML parser) to compile properly
RUN apt-get update && apt-get install -y \
    gcc \
    libxml2-dev \
    libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

# Step 4: Copy requirements first (Docker caches this layer)
# If requirements.txt hasn't changed, Docker skips re-installing
# This makes subsequent deploys much faster
COPY requirements.txt .

# Step 5: Install Python packages
RUN pip install --no-cache-dir -r requirements.txt

# Step 6: Copy the rest of your project
# The .dockerignore file controls what gets copied (see below)
COPY . .

# Step 7: Create directory for the SQLite database
# Render's free tier doesn't have persistent storage, but this
# lets the app run without crashing on startup
RUN mkdir -p /app/data

# Step 8: Expose the port (documentation only — Render uses $PORT)
EXPOSE 8000

# Step 9: Start command
# $PORT is provided by Render automatically
# --workers 2 = handle 2 requests simultaneously
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2"]
