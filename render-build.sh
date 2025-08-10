#!/usr/bin/env bash
set -e
apt-get update
apt-get install -y stockfish
pip install --upgrade pip
pip install -r requirements.txt
