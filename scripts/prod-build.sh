
#!/bin/bash
set -e
bash ./scripts/docker-run.sh docker/compose.dev.yml dashlab-prod mongo splitbox-api-prod
