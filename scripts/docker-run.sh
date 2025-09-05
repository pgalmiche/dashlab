#!/bin/bash
set -e  # Exit on any error

COMPOSE_FILE=$1
shift
SERVICES=("$@")  # Make services an array

# Optional environment variables
ENV_FILE=${ENV_FILE_PATH:-".env"}        # Default local env file
OVERRIDE_FILE=${OVERRIDE_FILE_PATH:-""}  # Optional override compose file

if [ -z "$COMPOSE_FILE" ] || [ ${#SERVICES[@]} -eq 0 ]; then
    echo "Usage: $0 <compose-file> <service1> [service2 ...]"
    exit 1
fi

echo "Starting services: ${SERVICES[*]} using compose file: $COMPOSE_FILE"
echo "Using env file: $ENV_FILE"

# Prepare docker-compose arguments
DOCKER_COMPOSE_ARGS=(--env-file "$ENV_FILE" -f "$COMPOSE_FILE")
if [ -n "$OVERRIDE_FILE" ]; then
    echo "Using override file: $OVERRIDE_FILE"
    DOCKER_COMPOSE_ARGS+=(-f "$OVERRIDE_FILE")
fi

# Build and start the specified services
docker compose "${DOCKER_COMPOSE_ARGS[@]}" up --build "${SERVICES[@]}"
exit_code=$?

echo "Services stopped or exited, cleaning up..."

# Bring everything down and remove orphans and volumes
docker compose "${DOCKER_COMPOSE_ARGS[@]}" down --remove-orphans --volumes

# Cleanup dangling images
docker image prune -f

# Cleanup stopped containers
docker container prune -f

# Cleanup unused volumes (use with caution)
docker volume prune -f

echo "Cleanup complete."
exit $exit_code
