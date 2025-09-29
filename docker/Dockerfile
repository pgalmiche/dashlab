# Stage 1: dev-env with all dependencies (prod + dev)
FROM python:3.11-slim AS dev-env

# Copy uv binaries for fast installs
COPY --from=ghcr.io/astral-sh/uv:0.7.21 /uv /uvx /bin/

WORKDIR /usr/src/app

# add git for git-based dependencies
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Copy dependency files only (no source code)
COPY pyproject.toml ./

# Install prod + dev dependencies
RUN uv pip install ".[docs, tests]" --system

# No source copy here; code will be bind-mounted in dev

# ------------------------------------

# Stage 2: runtime with only prod dependencies
FROM python:3.12-slim AS runtime

COPY --from=ghcr.io/astral-sh/uv:0.7.21 /uv /uvx /bin/

WORKDIR /usr/src/app

# Install curl for healthchecks
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Copy prod dependency file only
COPY pyproject.toml ./

# Install only prod dependencies
RUN uv pip install -r pyproject.toml --system

# Copy application source code for production
COPY . .

EXPOSE 7777

# This command was single thread, making the app freeze too much
# CMD ["gunicorn", "-b", "0.0.0.0:7777", "app.api.dashboard:server"]

CMD ["gunicorn","--workers","2","--threads","4","--worker-class","gthread","--timeout","120","--keep-alive","30","--log-level","warning","-b","0.0.0.0:7777","app.api.dashboard:server"]
