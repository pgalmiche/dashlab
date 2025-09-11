# Stage 1: base image
FROM python:3.11-slim AS docs-env

# Set working directory
WORKDIR /usr/src/app

# Install git (needed for git-based dependencies)
RUN apt-get update && apt-get install -y git curl && rm -rf /var/lib/apt/lists/*

# Copy pyproject.toml only (for caching)
COPY pyproject.toml ./

# Install uv binary for fast dependency installs
RUN pip install uv

# Install docs dependencies
RUN uv pip install ".[docs]" --system

# Copy the full project
COPY . .

# Build docs
RUN sphinx-build docs/src/ /tmp/public

# Serve docs
CMD ["python3", "-m", "http.server", "8000", "--directory", "/tmp/public"]
