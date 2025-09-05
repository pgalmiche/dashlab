#!/bin/bash
set -e

COMPOSE_FILE="docker/compose.prod.yml"

# Get all services except caddy
SERVICES=$(docker compose -f "$COMPOSE_FILE" config --services | grep -v '^caddy$')

# Optional: path to local .env
ENV_FILE_PATH="../.env"

# Optional: path to override compose file for local dev
OVERRIDE_FILE_PATH="docker/compose.prod.override_for_dev.yml"

# Pass them to your docker-run.sh script
ENV_FILE_PATH="$ENV_FILE_PATH" OVERRIDE_FILE_PATH="$OVERRIDE_FILE_PATH" \
bash ./scripts/docker-run.sh "$COMPOSE_FILE" $SERVICES
