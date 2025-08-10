#!/usr/bin/env bash
set -euxo pipefail

echo "Python version:"
python3 --version || true

echo "Updating apt and installing stockfish..."
apt-get update
apt-get install -y stockfish

echo "Stockfish path & version:"
which stockfish || true
stockfish -version || true

echo "Installing Python dependencies..."
pip install --upgrade pip
pip install --no-cache-dir -r requirements.txt
