#!/usr/bin/env bash
set -e
echo "Installing Majestic via Docker..."
docker compose up -d
echo "✓ Majestic running in Docker. Access via: docker exec -it majestic majestic"
