FROM python:3.12-slim

# Copy uv binaries from official uv image (faster, no pip install)
COPY --from=ghcr.io/astral-sh/uv:0.7.21 /uv /uvx /bin/

WORKDIR /usr/src/app

# Copy dependency files to install deps (before mounting source)
COPY pyproject.toml ./

# Install main + dev dependencies for local dev
RUN uv pip install -r pyproject.toml --system


