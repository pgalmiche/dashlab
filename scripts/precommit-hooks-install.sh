#!/usr/bin/env bash
set -euo pipefail

# Constants
HOOK_PATH=".git/hooks/pre-commit"
COMPOSE_FILE="./docker/compose.dev.yml"  # Adjust if needed

# Create the pre-commit Git hook
echo "Installing Git pre-commit hook..."

cat > "$HOOK_PATH" <<EOF
#!/bin/sh
# Run pre-commit inside Docker Compose with proper user permissions

# Run pre-commit inside Docker Compose and capture exit code
bash ./scripts/docker-run-container.sh docker/compose.dev.yml precommit
exit_code=\$?
exit \$exit_code

EOF

# Make the hook executable
chmod +x "$HOOK_PATH"

echo "✅ Pre-commit Git hook installed successfully at $HOOK_PATH"
echo "🔁 It will run through Docker Compose every time you commit."
