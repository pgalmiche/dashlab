# Use an official Python slim image
FROM python:3.11-slim

# Install git (needed by some pre-commit hooks)
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Install pre-commit
RUN pip install --no-cache-dir pre-commit ruff

ARG USER_ID=1000
ARG GROUP_ID=1000

RUN groupadd -g $GROUP_ID devgroup && \
    useradd -m -u $USER_ID -g $GROUP_ID devuser

USER devuser

# Set working directory inside container
WORKDIR /usr/src/app
