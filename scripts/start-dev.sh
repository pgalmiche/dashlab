#!/bin/bash
set -e  # Exit on any error

# Stop and remove any old containers and networks for these services to avoid conflicts
docker compose -f docker/compose.dev.yml down --remove-orphans

# Build and start the specified services with fresh containers
docker compose -f docker/compose.dev.yml up --build dashlab mongo

# Clean up dangling images after build (optional but good practice)
docker image prune -f

# Optionally: clean up all stopped containers (use with caution)
docker container prune -f

echo "Containers started and cleanup done once stopped."
