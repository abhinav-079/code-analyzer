#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo "=========================================================="
echo "      Code Quality Analyzer — Deployment Utility          "
echo "=========================================================="
echo ""
echo "Select deployment option:"
echo "  1) Run locally / on local network (host 0.0.0.0, port 5001)"
echo "  2) Run via Docker Container (docker-compose)"
echo "  3) View Cloud Deployment Guide (Render, Railway, Fly.io)"
echo ""
read -p "Enter choice [1-3]: " choice

case "$choice" in
  1)
    echo "Starting Code Quality Analyzer on 0.0.0.0:5001..."
    if [ -f "./.venv/bin/python" ]; then
      PYTHON_BIN="./.venv/bin/python"
    else
      PYTHON_BIN="python3"
    fi
    export HOST="0.0.0.0"
    export PORT="5001"
    exec "$PYTHON_BIN" app.py
    ;;
  2)
    echo "Building and starting Docker container..."
    if command -v docker &> /dev/null; then
      docker compose up --build -d
      echo "Container started! App running at http://localhost:5001"
    else
      echo "Error: Docker is not installed or not in PATH."
      exit 1
    fi
    ;;
  3)
    echo ""
    echo "--- 1-Click Cloud Deployment Options ---"
    echo ""
    echo "A) Render (Free & Recommended):"
    echo "   1. Push this project to a GitHub repository."
    echo "   2. Log in to https://render.com and click 'New +' -> 'Web Service'."
    echo "   3. Select your repo. Render will automatically detect render.yaml / requirements.txt."
    echo "   4. Start Command: gunicorn wsgi:app"
    echo ""
    echo "B) Railway:"
    echo "   1. Push to GitHub."
    echo "   2. In https://railway.app, click 'New Project' -> 'Deploy from GitHub repo'."
    echo "   3. Railway will automatically pick up the Procfile and deploy."
    echo ""
    echo "C) Fly.io:"
    echo "   1. Run: fly launch"
    echo "   2. Run: fly deploy"
    echo ""
    ;;
  *)
    echo "Invalid option. Exiting."
    exit 1
    ;;
esac
