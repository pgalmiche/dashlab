# Stage 1: dev-env with all dependencies (prod + dev)
FROM python:3.11-slim AS dev-env

# Copy uv binaries for fast installs
COPY --from=ghcr.io/astral-sh/uv:0.7.21 /uv /uvx /bin/

WORKDIR /usr/src/app

# add git for git-based dependencies
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Copy dependency files only (no source code)
COPY pyproject.toml requirements-dev.txt ./

# Install prod + dev dependencies
RUN uv pip install -r pyproject.toml --system
RUN uv pip install -r requirements-dev.txt --system

# Install Git-based dependencies separately (PEP 508 incompatible)
RUN pip install git+https://github.com/bashtage/sphinx-material.git

# No source copy here; code will be bind-mounted in dev

# ------------------------------------

# Stage 2: runtime with only prod dependencies
FROM python:3.12-slim AS runtime

COPY --from=ghcr.io/astral-sh/uv:0.7.21 /uv /uvx /bin/

WORKDIR /usr/src/app

# Copy prod dependency file only
COPY pyproject.toml ./

# Install only prod dependencies
RUN uv pip install -r pyproject.toml --system

# Copy application source code for production
COPY . .

EXPOSE 7777

CMD ["gunicorn", "-b", "0.0.0.0:7777", "app.api.dashboard:server"]
