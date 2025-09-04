#!/bin/bash
set -e
bash ./scripts/docker-run.sh docker/compose.dev.yml dashlab mongo splitbox-api-prod
