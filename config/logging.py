import logging
import sys
from logging.config import dictConfig

from config.settings import settings  # Your settings module


def setup_logging():
    """Configure logging for the application."""
    log_level = "DEBUG" if settings.DEBUG else "INFO"

    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,  # Keep libraries' loggers active
        "formatters": {
            "standard": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            },
            "json": {
                "format": '{"time": "%(asctime)s", "logger": "%(name)s", "level": "%(levelname)s", "message": "%(message)s"}',
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "stream": sys.stdout,
                "formatter": "standard",
            },
            # Optional: file handler example
            # "file": {
            #     "class": "logging.FileHandler",
            #     "filename": "app.log",
            #     "formatter": "standard",
            #     "level": "INFO",
            # },
        },
        "root": {
            "handlers": ["console"],
            "level": log_level,
        },
        "loggers": {
            # Disable noisy loggers if needed
            "uvicorn.error": {
                "level": "INFO",
                "handlers": ["console"],
                "propagate": False,
            },
            "uvicorn.access": {
                "level": "INFO",
                "handlers": ["console"],
                "propagate": False,
            },
        },
    }

    dictConfig(logging_config)
