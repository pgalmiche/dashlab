#!/bin/bash
set -e  # Exit on any error

COMPOSE_FILE=$1
shift
SERVICES="$@"

if [ -z "$COMPOSE_FILE" ] || [ -z "$SERVICES" ]; then
  echo "Usage: $0 <compose-file> <service1> [service2 ...]"
  exit 1
fi

echo "Starting services: $SERVICES using compose file: $COMPOSE_FILE"

# Build and start the specified services
docker compose -f "$COMPOSE_FILE" up --build $SERVICES

echo "Services stopped or exited, cleaning up..."

# Bring everything down and remove orphans and volumes
docker compose -f "$COMPOSE_FILE" down --remove-orphans --volumes

# Cleanup dangling images
docker image prune -f

# Cleanup stopped containers
docker container prune -f

# Cleanup unused volumes (use with caution)
docker volume prune -f

echo "Cleanup complete."

