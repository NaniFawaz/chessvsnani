FROM python:3.11-slim

# Install Stockfish (works inside the container)
RUN apt-get update \
 && apt-get install -y --no-install-recommends stockfish \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY . .

# Run with gunicorn and bind to Render's $PORT (fallback 8000 locally)
CMD exec gunicorn --bind 0.0.0.0:${PORT:-8000} app:app
