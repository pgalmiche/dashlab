FROM python:3.10-slim

# Set environment variables
ENV DASH_DEBUG=False
ENV DASH_ENV="production"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    gnupg2 \
    sudo \
    debian-keyring \
    debian-archive-keyring \
    apt-transport-https \
    ca-certificates \
    && apt-get clean

# Install Caddy
RUN curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg && \
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list && \
    apt-get update && \
    apt-get install -y caddy

# Install Poetry and Python dependencies
COPY pyproject.toml ./
RUN pip install poetry && \
    poetry config virtualenvs.create false && \
    poetry install --no-ansi --without dev

# Copy application code
WORKDIR /usr/src/app
COPY . .

# Copy Caddyfile
COPY Caddyfile /etc/caddy/Caddyfile

# Expose HTTP, HTTPS, and app ports
EXPOSE 80
EXPOSE 443
EXPOSE 7777

# Add entrypoint script
COPY docker-entrypoint.sh /usr/bin/docker-entrypoint.sh
RUN chmod +x /usr/bin/docker-entrypoint.sh

# Use entrypoint to run both Gunicorn and Caddy
ENTRYPOINT ["/usr/bin/docker-entrypoint.sh"]
