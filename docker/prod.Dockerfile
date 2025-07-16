FROM python:3.10-slim

# Set environment variables
ENV DASH_DEBUG=False
ENV DASH_ENV="production"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install Poetry and Python dependencies
COPY pyproject.toml ./
RUN pip install poetry && \
    poetry config virtualenvs.create false && \
    poetry install --no-ansi --without dev

# Copy application code
WORKDIR /usr/src/app
COPY . .

EXPOSE 7777

CMD ["gunicorn", "-b", "0.0.0.0:7777", "dashboard:server"]
