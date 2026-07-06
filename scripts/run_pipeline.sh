#!/usr/bin/env bash
# Simple runner for the Docker-based pipeline
set -e

# build and start services
docker-compose up --build -d

# run playwright scraper explicitly
docker-compose run --rm playwright node scrape.js "$@"

# run processor (example)
docker-compose run --rm processor python scripts/analyze.py

echo "Pipeline run complete. Check ./data for outputs."
