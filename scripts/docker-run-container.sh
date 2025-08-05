#!/bin/bash
set -euo pipefail

# Usage: ./docker-run.sh <compose-file> <service-name>
if [ $# -lt 2 ]; then
    echo "Usage: $0 <compose-file> <service>"
    exit 1
fi

COMPOSE_FILE=$1
SERVICE=$2

echo "🔄 Running service '$SERVICE' from compose file '$COMPOSE_FILE'..."

docker compose -f "$COMPOSE_FILE" run --rm "$SERVICE"
