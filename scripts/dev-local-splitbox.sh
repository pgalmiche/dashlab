#!/bin/bash
set -e

# Use the override file for local splitbox-api image
export OVERRIDE_FILE_PATH=docker/compose.splitbox-dev-override.yml

# Call your existing docker-run.sh with compose file and services
bash ./scripts/docker-run.sh docker/compose.dev.yml dashlab mongo splitbox-api-prod
