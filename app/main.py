from app.api.dashboard import app
from config.logging import setup_logging

setup_logging()

import logging

logger = logging.getLogger(__name__)

if __name__ == "__main__" and DASH_ENV == "development":
    app.run(host="0.0.0.0", port=7777, debug=DEBUG_MODE)
    logger.info("App started")
