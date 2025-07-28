import logging

from app.api.dashboard import app
from config.logging import setup_logging
from config.settings import settings

setup_logging()

# add logger
logger = logging.getLogger(__name__)

if __name__ == '__main__' and settings.env == 'development':
    logger.info('App starting...')
    app.run(host='0.0.0.0', port=7777, debug=settings.debug)
